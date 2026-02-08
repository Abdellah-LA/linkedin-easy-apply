"""
Auto-applier: Easy Apply modal — contact step (email dropdown) + click Suivant through steps.
"""
import asyncio
import random
import re
from pathlib import Path
from typing import Any, Dict

# Default text when we have no answer (user: "just write none"); repeat to meet char limit if needed
TEXT_FALLBACK = "none"

from playwright.async_api import Page

from browser_engine import human_delay
from config import (
    CV_PATH,
    DEFAULT_LOCATION_CITY,
    EASY_APPLY_EMAIL,
    EASY_APPLY_YEARS_DEFAULT,
    RESUME_PATH,
    USE_GEMINI_FOR_CV,
    WORK_AUTHORIZATION_ANSWER,
    WORK_NEED_SPONSORSHIP_ANSWER,
)
from logger_config import logger

from cv_reader import get_answer_for_question
from gemini_cv import get_answer_any_question_gemini, get_answer_from_options

# Modal and buttons
EASY_APPLY_MODAL = "[data-test-modal], .jobs-easy-apply-modal, [role='dialog'], .jobs-easy-apply-content"
NEXT_BUTTON = "button:has-text('Suivant'), button:has-text('Next'), button[aria-label*='Next']"
VERIFY_BUTTON = "button:has-text('Vérifier'), button:has-text('Verify')"
# Submit / Send application — FR: Soumettre, Envoyer la candidature; EN: Submit, Send application
# Button can be <button> or <a>/div with button role; text may be in child node
SUBMIT_BUTTON_SELECTORS = [
    "button:has-text('Envoyer la candidature')",
    "button:has-text('Send application')",
    "button:has-text('Soumettre')",
    "button:has-text('Submit')",
    "button:has-text('Envoyer')",
    "[role='button']:has-text('Envoyer la candidature')",
    "[role='button']:has-text('Send application')",
    "a:has-text('Envoyer la candidature')",
    "a:has-text('Send application')",
    ".artdeco-button:has-text('Envoyer la candidature')",
    ".artdeco-button:has-text('Send application')",
]
# After submit, LinkedIn shows "Candidature envoyée" with Terminé (FR) / OK / Done — must click to close
CONFIRMATION_BUTTON = "button:has-text('Terminé'), button:has-text('OK'), button:has-text('Fermer'), button:has-text('Done'), button:has-text('Fermer la fenêtre'), button[aria-label*='Fermer'], button[aria-label*='Close']"
CLOSE_BUTTON = "button[aria-label*='Fermer'], button[aria-label*='Close'], button[data-test-modal-id] button, [data-test-modal] button[aria-label*='Fermer'], [data-test-modal] button[aria-label*='Close'], .artdeco-modal__dismiss"
EASY_APPLY_MODAL_ID = "[data-test-modal-id='easy-apply-modal']"
# "Save this application?" dialog: click Discard / Supprimer to close without saving (FR + EN)
DISCARD_BUTTON_SELECTORS = [
    "button:has-text('Supprimer')",
    "button:has-text('Discard')",
    "button:has-text('Delete')",
    "button:has-text('Ne pas enregistrer')",
    'button:has-text("Don\'t save")',
]

# Validation error phrases (EN/FR) — when visible in modal we skip this job and close without saving
VALIDATION_ERROR_PHRASES = (
    "enter a decimal number larger than 0.0",
    "enter a whole number between 0 and 99",
    "please enter a valid",
    "veuillez saisir une réponse valable",
    "veuillez saisir",
    "valid response",
    "réponse valable",
    "this field is required",
    "ce champ est obligatoire",
)


def _normalize_question_key(label: str) -> str:
    """Normalize label for matching form_answers (lowercase, no extra spaces, key phrases)."""
    if not label:
        return ""
    key = re.sub(r"\s+", " ", label.lower().strip())
    # Map common variants to a canonical key
    if "années" in key or "years" in key or "experience" in key:
        return "years_of_experience"
    if "salaire" in key or "salary" in key:
        return "salary"
    if "visa" in key or "sponsorship" in key:
        return "visa"
    if "linkedin" in key or "url" in key:
        return "linkedin_url"
    return key[:80]


def _find_answer_for_question(question_label: str, form_answers: Dict[str, Any]) -> Any:
    """Match question label to form_answers (by normalized key or substring)."""
    norm = _normalize_question_key(question_label)
    if norm and norm in form_answers:
        return form_answers[norm]
    for key, value in form_answers.items():
        if key.lower() in question_label.lower() or question_label.lower() in key.lower():
            return value
    return form_answers.get(question_label) or form_answers.get(norm)


async def _fill_input(page: Page, selector: str, value: Any) -> bool:
    """Fill a single input/select. Handles text, dropdown, radio."""
    if value is None or value == "":
        return True
    str_val = str(value).strip()
    await human_delay(0.5, 1.5)
    try:
        el = page.locator(selector).first
        tag = await el.evaluate("el => el.tagName.toLowerCase()")
        role = await el.get_attribute("role")
        if tag == "select" or role == "listbox":
            await el.select_option(str_val, timeout=8000)
            return True
        if tag == "input":
            type_ = await el.get_attribute("type")
            if type_ == "file":
                if Path(str_val).exists():
                    await el.set_input_files(str_val, timeout=8000)
                    return True
                return False
            await el.fill(str_val, timeout=8000)
            return True
        # contenteditable or textarea
        await el.fill(str_val, timeout=8000)
        return True
    except Exception as e:
        logger.debug("Fill failed for %s: %s", selector[:50], e)
        return False


async def fill_easy_apply_form(page: Page, form_answers: Dict[str, Any], resume_path: str = "") -> bool:
    """
    Iterate the Easy Apply modal: for each visible field, try to match to form_answers and fill.
    If a file input is found and resume_path is set, upload the resume.
    """
    modal = page.locator(EASY_APPLY_MODAL).first
    try:
        await modal.wait_for(state="visible", timeout=12000)
    except Exception as e:
        logger.warning("Easy Apply modal did not appear: %s", e)
        return False

    used_resume = False
    max_steps = 15
    for step in range(max_steps):
        await human_delay(1, 3)
        # Find all inputs in modal (input, select, textarea, [contenteditable])
        inputs = await modal.locator(
            "input:visible, select:visible, textarea:visible, [contenteditable='true']:visible"
        ).all()
        filled_any = False
        for inp in inputs:
            try:
                label = await inp.evaluate(
                    """el => {
                    const id = el.id;
                    if (id) {
                        const label = document.querySelector('label[for="'+id+'"]');
                        if (label) return label.innerText || '';
                    }
                    let p = el.parentElement;
                    for (let i = 0; i < 5 && p; i++) {
                        const l = p.querySelector('label');
                        if (l) return l.innerText || '';
                        p = p.parentElement;
                    }
                    return el.getAttribute('placeholder') || el.getAttribute('aria-label') || '';
                }"""
                )
                type_ = await inp.get_attribute("type")
                if type_ == "file":
                    if resume_path and Path(resume_path).exists() and not used_resume:
                        await human_delay(0.5, 1)
                        await inp.set_input_files(resume_path, timeout=10000)
                        used_resume = True
                        filled_any = True
                        logger.info("Uploaded resume to Easy Apply form")
                    continue
                answer = _find_answer_for_question(label or "", form_answers)
                if answer is None or answer == "":
                    continue
                # Try to fill by selector (we have the element)
                await human_delay(0.3, 0.8)
                try:
                    if type_ == "checkbox" or type_ == "radio":
                        if str(answer).lower() in ("true", "yes", "1", "oui"):
                            await inp.check(timeout=5000)
                        else:
                            await inp.uncheck(timeout=5000)
                        filled_any = True
                    else:
                        await inp.fill(str(answer), timeout=8000)
                        filled_any = True
                except Exception as e:
                    logger.debug("Fill single field failed: %s", e)
            except Exception as e:
                logger.debug("Field iteration error: %s", e)

        # Next or Submit (Envoyer la candidature / Send application)
        if await _click_submit_if_visible(modal, page):
            return True
        next_btn = modal.locator(NEXT_BUTTON).first
        if await next_btn.is_visible():
            await human_delay(1, 2)
            await next_btn.click(timeout=10000)
            filled_any = True
            continue
        if not filled_any and step > 0:
            logger.warning("No Next/Submit found; stopping form fill")
            break
    return False


async def _fill_additional_questions(modal) -> None:
    """
    Fill all Additional Questions: years (experience map), Yes/No (experience map),
    work authorization (No), and open-ended (Gemini from CV). Handles input, select, radio, checkbox.
    """
    cv_path = CV_PATH or ""
    get_label_js = """el => {
        const id = el.id;
        if (id) {
            const label = document.querySelector('label[for="'+id+'"]');
            if (label) return label.innerText || '';
        }
        let p = el.parentElement;
        for (let i = 0; i < 8 && p; i++) {
            const l = p.querySelector('label');
            if (l) return l.innerText || '';
            const legend = p.querySelector('legend');
            if (legend) return legend.innerText || '';
            p = p.parentElement;
        }
        return el.getAttribute('placeholder') || el.getAttribute('aria-label') || '';
    }"""
    # Required = has * in label text, or required/aria-required on element
    get_label_and_required_js = """el => {
        const id = el.id;
        let labelText = '';
        if (id) {
            const label = document.querySelector('label[for="'+id+'"]');
            if (label) labelText = label.innerText || '';
        }
        if (!labelText) {
            let p = el.parentElement;
            for (let i = 0; i < 8 && p; i++) {
                const l = p.querySelector('label');
                if (l) { labelText = l.innerText || ''; break; }
                const legend = p.querySelector('legend');
                if (legend) { labelText = legend.innerText || ''; break; }
                p = p.parentElement;
            }
        }
        if (!labelText) labelText = el.getAttribute('placeholder') || el.getAttribute('aria-label') || '';
        const required = el.required === true || el.getAttribute('aria-required') === 'true' || (labelText && labelText.indexOf('*') !== -1);
        return { label: labelText, required: !!required };
    }"""

    # Inputs: number, text, and textarea — fill required fields; when no answer use "none" (repeat to meet char limit if needed)
    inputs = await modal.locator("input[type='number']:visible, input[type='text']:visible, textarea:visible").all()
    for inp in inputs:
        try:
            info = await inp.evaluate(get_label_and_required_js)
            if not info.get("required"):
                continue
            # Never overwrite: skip if field already has a value
            try:
                existing = await inp.input_value()
                if (existing or "").strip():
                    continue
            except Exception:
                pass
            label_str = (info.get("label") or "").strip()
            tag = await inp.evaluate("el => el.tagName.toLowerCase()")
            is_number = await inp.get_attribute("type") == "number"
            answer = get_answer_for_question(
                label_str,
                years_default=EASY_APPLY_YEARS_DEFAULT,
                cv_path=cv_path,
                use_gemini=USE_GEMINI_FOR_CV,
            )
            if answer is None and label_str.strip():
                answer = get_answer_any_question_gemini(label_str)
            label_lower = (label_str or "").lower()
            # Only rating-style fields (frontend*, backend*, microservice*) use decimals; years of experience use whole number (0-99)
            rating_labels = ("frontend", "backend", "microservice", "microservices", "api", "database", "devops", "fullstack", "mobile", "cloud", "security", "testing", "data")
            wants_decimal = any(k in label_lower for k in rating_labels)
            wants_whole_number = ("years" in label_lower and "experience" in label_lower) and not wants_decimal

            if answer is None or (str(answer).strip() in ("", "N/A") and tag != "input" and not is_number):
                if wants_decimal:
                    answer = "8.0" if ("frontend" in label_lower or "backend" in label_lower) else "5.0"
                elif is_number:
                    answer = "3" if wants_whole_number else "0"
                else:
                    answer = TEXT_FALLBACK
            text_val = str(answer).strip()
            if not text_val and not is_number:
                text_val = TEXT_FALLBACK
            # Decimal fields (rating only): 8.0 / 5.0
            if wants_decimal and text_val.lower() in ("yes", "no", "oui", "non", "n/a", ""):
                text_val = "8.0" if ("frontend" in label_lower or "backend" in label_lower) else "5.0"
            elif wants_decimal and not re.match(r"^-?\d+(\.\d+)?$", text_val):
                text_val = "8.0" if ("frontend" in label_lower or "backend" in label_lower) else "5.0"
            elif wants_decimal and re.match(r"^-?\d+(\.\d+)?$", text_val):
                try:
                    v = float(text_val)
                    if v < 0.1:
                        text_val = "8.0" if ("frontend" in label_lower or "backend" in label_lower) else "5.0"
                except (TypeError, ValueError):
                    text_val = "5.0"
            # Whole number fields (years of experience): avoid decimal — "Enter a whole number between 0 and 99"
            if wants_whole_number and re.match(r"^-?\d+(\.\d+)?$", text_val):
                try:
                    text_val = str(int(float(text_val)))
                except (TypeError, ValueError):
                    text_val = "3"
            # If textarea and there's a character limit, repeat "none " until we meet it (user: repeat none until required chars)
            if tag == "textarea" or (tag == "input" and not is_number):
                try:
                    max_len = await inp.get_attribute("maxlength")
                    if max_len:
                        max_len = int(max_len)
                    else:
                        # Parse helper text e.g. "0/1 440" or "1440 caractères autorisés" — use largest number as limit
                        helper = await inp.evaluate("""el => {
                            const id = el.getAttribute('aria-describedby');
                            if (!id) return null;
                            const node = document.getElementById(id);
                            const m = (node?.innerText || '').match(/\\d+/g);
                            return m ? Math.max(...m.map(Number)) : null;
                        }""")
                        if helper is not None:
                            try:
                                max_len = int(helper) if isinstance(helper, (int, float)) else int(helper[0]) if isinstance(helper, list) and helper else None
                            except (TypeError, ValueError, IndexError):
                                max_len = None
                        else:
                            max_len = None
                    if max_len and len(text_val) < max_len and text_val.lower() == TEXT_FALLBACK:
                        text_val = ((TEXT_FALLBACK + " ") * (max_len // (len(TEXT_FALLBACK) + 1) + 1))[:max_len]
                except Exception:
                    pass
            await inp.fill(text_val, timeout=5000)
            logger.debug("Filled required '%s' with %s", label_str[:50], text_val[:50] if len(text_val) > 50 else text_val)
            # If this is Location (city) and we filled the default city, try to pick from dropdown if it appears
            label_lower = label_str.lower()
            if (
                "location" in label_lower
                and "city" in label_lower
                and str(answer).strip() == (DEFAULT_LOCATION_CITY or "").strip()
            ):
                await asyncio.sleep(1.2)
                try:
                    options = modal.locator("[role='option'], .artdeco-typeahead-item")
                    if await options.count() > 0:
                        await options.first.click(timeout=2000)
                        logger.debug("Selected location from dropdown")
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Fill input: %s", e)

    # Selects (dropdowns) — only fill required fields (marked with *). Use API to pick when options don't match.
    selects = await modal.locator("select:visible").all()
    for sel in selects:
        try:
            info = await sel.evaluate(get_label_and_required_js)
            if not info.get("required"):
                continue
            # Never overwrite: skip if a real option is already selected
            try:
                selected = await sel.evaluate("""el => {
                    const v = (el.value || '').trim();
                    const opt = el.options[el.selectedIndex];
                    const text = (opt ? opt.textContent || '' : '').trim().toLowerCase();
                    if (!v || text === 'select an option' || text === 'choose' || text === '') return false;
                    return true;
                }""")
                if selected:
                    continue
            except Exception:
                pass
            label_str = (info.get("label") or "").strip()
            # Collect real option texts (skip placeholders)
            option_texts: list[str] = []
            for opt in await sel.locator("option").all():
                text = (await opt.text_content() or "").strip()
                v = await opt.get_attribute("value")
                if not text or text.lower() in ("select an option", "choose", ""):
                    continue
                option_texts.append(text)
            if not option_texts:
                continue
            label_lower = label_str.lower()
            answer = get_answer_for_question(
                label_str,
                years_default=EASY_APPLY_YEARS_DEFAULT,
                cv_path=cv_path,
                use_gemini=USE_GEMINI_FOR_CV,
            )
            if answer is None and label_str.strip():
                answer = get_answer_any_question_gemini(label_str)
            # Legal status in Canada: user is Moroccan, not Canadian citizen -> select "No status" or "Other"
            if "legal status" in label_lower and "canada" in label_lower:
                for o in option_texts:
                    o_trim = (o or "").strip()
                    if o_trim in ("No status", "Other", "Open Work Visa"):
                        answer = o_trim
                        break
            # If answer doesn't match any option, use API to pick from the list (Work Authorization, Hybrid, Relocate, etc.)
            answer_lower = (str(answer).strip().lower()) if answer else ""
            matches = [o for o in option_texts if answer_lower and (answer_lower in o.lower() or o.lower() in answer_lower or answer_lower == o.lower())]
            # Experience Yes/No dropdowns often use "Oui"/"Non" (French): map Yes/No to Oui/Non when no match
            if not matches and answer_lower in ("yes", "no"):
                oui_non = "Oui" if answer_lower == "yes" else "Non"
                for o in option_texts:
                    if (o or "").strip().lower() == oui_non.lower():
                        matches = [o]
                        answer = o
                        answer_lower = (o or "").strip().lower()
                        break
            if not matches and option_texts:
                api_choice = get_answer_from_options(label_str, option_texts)
                if api_choice:
                    answer = api_choice
                    answer_lower = answer.strip().lower()
                else:
                    answer = random.choice(option_texts)  # user: when stuck improvise/random
                    answer_lower = answer.strip().lower()
            elif matches:
                answer = matches[0]
            if not answer:
                continue
            try:
                await sel.select_option(value=answer, timeout=3000)
            except Exception:
                try:
                    await sel.select_option(label=answer, timeout=3000)
                except Exception:
                    for opt in await sel.locator("option").all():
                        text = await opt.text_content()
                        if text and (answer_lower in (text or "").lower() or (text or "").lower() in answer_lower):
                            await opt.click(timeout=3000)
                            break
            logger.debug("Selected required '%s' -> %s", label_str[:50], answer)
        except Exception as e:
            logger.debug("Fill select: %s", e)

    # Consent / approval checkboxes: always check "I consent", "I agree", privacy policy, etc. so we can complete the application
    consent_keywords = ("consent", "i consent", "agree", "privacy", "declare", "read and understand", "approve", "accept", "authorize")
    try:
        checkboxes = await modal.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            try:
                if await cb.is_checked():
                    continue
                # Get label or surrounding text
                context = await cb.evaluate("""el => {
                    const label = el.closest('label') || (el.id && document.querySelector('label[for="' + el.id + '"]'));
                    const block = el.closest('fieldset') || el.closest('[role="group"]') || el.closest('.fb-dash-form-element') || el.closest('[class*="form-element"]') || el.parentElement?.parentElement;
                    const text = (label?.innerText || block?.innerText || '').trim().substring(0, 300).toLowerCase();
                    return text;
                }""")
                if not context:
                    continue
                if not any(k in context for k in consent_keywords):
                    continue
                await cb.scroll_into_view_if_needed(timeout=3000)
                await cb.check(timeout=4000)
                logger.debug("Checked consent/approval checkbox: ~%s", context[:60])
            except Exception as e_cb:
                logger.debug("Consent checkbox: %s", e_cb)
    except Exception as e:
        logger.debug("Consent checkboxes block: %s", e)

    # Required checkbox groups (e.g. "How did you hear about this role?"): pick one at random, prefer LinkedIn (user: "juste choose random")
    try:
        checkbox_groups = await modal.locator("fieldset[data-test-checkbox-form-component]").all()
        for fieldset in checkbox_groups:
            try:
                is_required = await fieldset.evaluate("""el => !!el.querySelector('[class*="is-required"]') || el.getAttribute('aria-describedby')""")
                if not is_required:
                    continue
                checked_count = await fieldset.locator("input[type='checkbox']:checked").count()
                if checked_count > 0:
                    continue
                options = await fieldset.locator("[data-test-text-selectable-option]").all()
                if not options:
                    continue
                # Prefer option whose label is "LinkedIn", else pick random
                preferred = None
                for o in options:
                    lbl = await o.locator("[data-test-text-selectable-option__label]").first.get_attribute("data-test-text-selectable-option__label")
                    if lbl and "linkedin" in (lbl or "").lower():
                        preferred = o
                        break
                to_click = preferred or random.choice(options)
                inp = to_click.locator("input[type='checkbox']").first
                await inp.scroll_into_view_if_needed(timeout=2000)
                await inp.check(timeout=3000)
                logger.debug("Checked one option in required checkbox group (random/LinkedIn)")
            except Exception as e_cg:
                logger.debug("Required checkbox group: %s", e_cg)
    except Exception as e:
        logger.debug("Required checkbox groups block: %s", e)

    # LinkedIn custom multiple-choice: click labels with data-test-text-selectable-option__label (Yes/No)
    # so we don't rely on native input[type=radio] which may be hidden or missing
    linkedin_option_blocks_js = """el => {
        const block = el.closest('fieldset') || el.closest('[role="group"]') || el.closest('.fb-dash-form-element') || el.closest('[class*="form-element"]') || el.parentElement?.parentElement?.parentElement;
        if (!block) return null;
        const question = (block.innerText || '').trim().substring(0, 250);
        const labelEl = el.querySelector('[data-test-text-selectable-option__label]') || el;
        const value = (labelEl.getAttribute && labelEl.getAttribute('data-test-text-selectable-option__label')) || (labelEl.innerText || '').trim();
        const required = question.indexOf('*') >= 0 || !!(block.querySelector('[class*="is-required"]') || block.querySelector('input[aria-required="true"]'));
        const allLabels = [...block.querySelectorAll('[data-test-text-selectable-option]')].map(o => {
            const l = o.querySelector('[data-test-text-selectable-option__label]');
            return (l?.getAttribute?.('data-test-text-selectable-option__label') || l?.innerText || '').trim();
        }).filter(Boolean);
        return { question, value, required, allLabels };
    }"""
    try:
        linkedin_options = await modal.locator("[data-test-text-selectable-option]").all()
        seen_questions: set = set()
        for opt in linkedin_options:
            try:
                info = await opt.evaluate(linkedin_option_blocks_js)
                if not info or not (info.get("question") and info.get("value")):
                    continue
                q = (info.get("question") or "").strip()
                block_key = q[:100]
                if block_key in seen_questions:
                    continue
                if not info.get("required", "*" in q):
                    continue
                seen_questions.add(block_key)
                q_lower = q.lower()
                all_labels = info.get("allLabels") or []
                if not all_labels and info.get("value"):
                    all_labels = [info.get("value")]

                # Location/relocation questions: prefer "open to relocation" / "Prêt(e) à déménager" (user: always ready to relocate)
                location_keywords = ("montreal", "quebec", "situé", "eligible", "déménager", "relocat", "relocation", "province", "full time", "located", "work full time")
                is_location_question = any(k in q_lower for k in location_keywords)
                relocation_keywords = ("relocat", "déménager", "open to")
                target_label = None
                if is_location_question and all_labels:
                    for lbl in all_labels:
                        if any(r in (lbl or "").lower() for r in relocation_keywords):
                            target_label = lbl
                            break
                if target_label is None and all_labels:
                    # Prefer option that contains Yes/oui (not No/non)
                    for lbl in all_labels:
                        ll = (lbl or "").lower().strip()
                        if ("yes" in ll or "oui" in ll) and ll != "no" and not ll.startswith("no/"):
                            target_label = lbl
                            break
                if target_label is None and all_labels:
                    target_label = all_labels[0]

                if "right to work" in q_lower and ("canada" in q_lower or "country" in q_lower) and "sponsorship" not in q_lower:
                    answer_str = "No"
                elif "sponsorship" in q_lower and "visa" in q_lower and ("require" in q_lower or "need" in q_lower):
                    answer_str = "Yes"
                elif any(k in q_lower for k in ("criminal background", "background check", "employment verification", "reference check", "education check", "agree to partake")):
                    answer_str = "Yes"  # user: always say yes, clean person
                else:
                    answer_str = str(target_label or "Yes").strip()
                # For binary Yes/No we keep target_value for input selectors; for 3+ options we use target_label
                target_value = "Yes" if answer_str.lower() in ("yes", "oui") or (target_label and ("yes" in (target_label or "").lower() or "oui" in (target_label or "").lower())) else "No"
                if target_label and target_label not in ("Yes", "No"):
                    target_value = target_label  # use exact label for non-binary
                # LinkedIn DOM: Yes = value="1" + data-test-text-selectable-option__input="Yes", No = value="0" + ...="No"
                clicked = False
                try:
                    block = opt.locator("xpath=ancestor::fieldset[1] | ancestor::*[@role='group'][1] | ancestor::*[contains(@class,'fb-dash-form-element')][1] | ancestor::*[contains(@class,'form-element')][1]").first
                    # If we chose a specific label (e.g. "I am open to relocation"), find and check that option by label text
                    if target_value not in ("Yes", "No"):
                        try:
                            await block.evaluate(
                                """(block, chosenLabel) => {
                                    const opts = block.querySelectorAll('[data-test-text-selectable-option]');
                                    for (const o of opts) {
                                        const l = o.querySelector('[data-test-text-selectable-option__label]');
                                        const t = (l?.getAttribute?.('data-test-text-selectable-option__label') || l?.innerText || '').trim();
                                        if (t && (t === chosenLabel || t.includes(chosenLabel) || chosenLabel.includes(t))) {
                                            const input = o.querySelector('input');
                                            if (input) { input.scrollIntoView({block:'center'}); input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); return true; }
                                            l?.click(); return true;
                                        }
                                    }
                                }""",
                                target_value,
                            )
                            clicked = True
                            logger.debug("LinkedIn custom: selected '%s' for question ~%s", target_value[:50], block_key[:50])
                        except Exception:
                            pass
                    if not clicked and target_value in ("Yes", "No"):
                        # 1) Prefer native input.check() — data-test, value 1/0, value yes/no (lowercase), value Yes/No
                        for selector in (
                            f'input[type="radio"][data-test-text-selectable-option__input="{target_value}"]',
                            f'input[type="radio"][value="{"1" if target_value == "Yes" else "0"}"]',
                            f'input[type="radio"][value="{target_value.lower()}"]',
                            f'input[type="radio"][value="{target_value}"]',
                        ):
                            try:
                                radio_in_block = block.locator(selector).first
                                await radio_in_block.scroll_into_view_if_needed(timeout=3000)
                                await radio_in_block.check(timeout=4000)
                                clicked = True
                                logger.debug("LinkedIn custom: checked input %s for question ~%s", target_value, block_key[:50])
                                break
                            except Exception:
                                continue
                except Exception:
                    pass
                if not clicked and target_value in ("Yes", "No"):
                    try:
                        block = opt.locator("xpath=ancestor::fieldset[1] | ancestor::*[@role='group'][1] | ancestor::*[contains(@class,'fb-dash-form-element')][1] | ancestor::*[contains(@class,'form-element')][1]").first
                        option_with_label = block.locator(f'[data-test-text-selectable-option]:has([data-test-text-selectable-option__label="{target_value}"])').first
                        label_in_block = option_with_label.locator(f'[data-test-text-selectable-option__label="{target_value}"]').first
                        await label_in_block.scroll_into_view_if_needed(timeout=3000)
                        await label_in_block.click(force=True, timeout=4000)
                        clicked = True
                        logger.debug("LinkedIn custom: clicked label %s for question ~%s", target_value, block_key[:50])
                    except Exception:
                        pass
                if not clicked:
                    try:
                        # JS: works for both "Yes"/"No" (value 1/0) and long labels (find by label text)
                        await opt.evaluate(
                            """(el, val) => {
                                const block = el.closest('fieldset') || el.closest('[role="group"]') || el.closest('.fb-dash-form-element') || el.closest('[class*="form-element"]') || el.parentElement?.parentElement?.parentElement;
                                const opts = block?.querySelectorAll('[data-test-text-selectable-option]');
                                const v = (val || '').toLowerCase();
                                for (const o of opts || []) {
                                    const labelEl = o.querySelector('[data-test-text-selectable-option__label]');
                                    const t = (labelEl?.getAttribute?.('data-test-text-selectable-option__label') || labelEl?.innerText || '').trim();
                                    const tl = (t || '').toLowerCase();
                                    const match = t === val || tl.includes(v) || v.includes(tl) || (v === 'yes' && (tl.includes('yes') || tl.includes('oui'))) || (v === 'no' && (tl.includes('no') || tl.includes('non')));
                                    if (t && match) {
                                        const input = o.querySelector('input');
                                        if (input) { input.scrollIntoView({block:'center'}); input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); return; }
                                        labelEl?.click(); return;
                                    }
                                }
                                const numVal = (val === 'Yes') ? '1' : '0';
                                const input = block?.querySelector('input[type="radio"][value="' + numVal + '"]') || block?.querySelector('input[data-test-text-selectable-option__input="' + val + '"]');
                                if (input) { input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); }
                            }""",
                            target_value,
                        )
                        clicked = True
                        logger.debug("LinkedIn custom (eval): set %s for ~%s", target_value[:50], block_key[:50])
                    except Exception:
                        pass
                if not clicked and target_value in ("Yes", "No"):
                    try:
                        block_fb = opt.locator("xpath=ancestor::fieldset[1] | ancestor::*[@role='group'][1] | ancestor::*[contains(@class,'fb-dash-form-element')][1] | ancestor::*[contains(@class,'form-element')][1]").first
                        label_any = block_fb.locator(f'[data-test-text-selectable-option__label="{target_value}"]').first
                        await label_any.scroll_into_view_if_needed(timeout=3000)
                        await label_any.click(force=True, timeout=4000)
                    except Exception:
                        try:
                            await opt.locator(f'[data-test-text-selectable-option__label="{target_value}"]').first.click(force=True, timeout=4000)
                        except Exception:
                            await opt.click(force=True, timeout=4000)
            except Exception as e:
                logger.debug("LinkedIn option fill: %s", e)
    except Exception as e:
        logger.debug("LinkedIn custom options block: %s", e)

    # Radio / checkbox — native inputs (include hidden so LinkedIn's styled radios are found)
    get_group_question_js = """el => {
        let p = el.closest('fieldset') || el.closest('[role="group"]') || el.parentElement;
        for (let i = 0; i < 12 && p; i++) {
            const legend = p.querySelector('legend');
            if (legend && (legend.innerText || '').trim().length > 10) return (legend.innerText || '').trim();
            const labels = p.querySelectorAll('label');
            for (const l of labels) {
                const t = (l.innerText || '').trim();
                if (t.length > 20 && !l.contains(el)) return t;
            }
            p = p.parentElement;
        }
        return '';
    }"""
    get_block_text_js = """el => {
        const p = el.closest('fieldset') || el.closest('[role="group"]') || el.parentElement?.parentElement;
        return (p?.innerText || '').trim();
    }"""
    radios = await modal.locator("input[type='radio'], input[type='checkbox']").all()
    seen_names = set()
    for r in radios:
        try:
            name = await r.get_attribute("name")
            if name and name in seen_names:
                continue
            group_label = await r.evaluate(get_group_question_js)
            block_text = await r.evaluate(get_block_text_js)
            block_lower = (block_text or "").lower()
            group_lower = (group_label or "").lower()
            combined_lower = block_lower + " " + group_lower
            # Only fill required fields: question has * or radio has aria-required
            is_required = "*" in (block_text or "") or "*" in (group_label or "") or await r.get_attribute("aria-required") == "true"
            if not is_required:
                if name:
                    seen_names.add(name)
                continue
            # Never overwrite: skip if this radio group already has a selection
            if name:
                already_checked = await modal.locator(f'input[type="radio"][name="{name}"]:checked').count() > 0
                if already_checked:
                    seen_names.add(name)
                    continue
            # Work authorization: "Are you legally authorized to work in Canada?" — use WORK_AUTHORIZATION_ANSWER (Yes/No from .env)
            is_work_auth = (
                ("right to work" in combined_lower and ("canada" in combined_lower or "country" in combined_lower) and "sponsorship" not in combined_lower)
                or ("authorized" in combined_lower and "work" in combined_lower and ("canada" in combined_lower or "country" in combined_lower))
                or ("autorisé" in combined_lower and "travailler" in combined_lower) or ("légalement" in combined_lower and "travailler" in combined_lower)
            )
            if is_work_auth:
                if name:
                    seen_names.add(name)
                want_yes = (WORK_AUTHORIZATION_ANSWER or "No").strip().lower() in ("yes", "oui", "1", "true")
                target_value = "Yes" if want_yes else "No"
                if name:
                    for sel in (f'input[type="radio"][data-test-text-selectable-option__input="{target_value}"][name="{name}"]', f'input[type="radio"][value="{"1" if want_yes else "0"}"][name="{name}"]', f'input[type="radio"][value="{target_value.lower()}"][name="{name}"]', f'input[type="radio"][value="{target_value}"][name="{name}"]'):
                        try:
                            await modal.locator(sel).first.check(timeout=3000)
                            logger.debug("Checked %s (work authorization, from .env)", target_value)
                            break
                        except Exception:
                            continue
                else:
                    try:
                        await r.evaluate("""(el, val) => {
                            const container = el.closest('fieldset') || el.closest('[role="group"]') || el.parentElement?.parentElement;
                            const numVal = (val === 'Yes') ? '1' : '0';
                            const input = container?.querySelector('input[data-test-text-selectable-option__input="' + val + '"]') || container?.querySelector('input[type="radio"][value="' + numVal + '"]') || container?.querySelector('input[type="radio"][value="' + val + '"]');
                            if (input) { input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); }
                            else { const lbl = container?.querySelector('[data-test-text-selectable-option__label="' + val + '"]'); if (lbl) lbl.click(); }
                        }""", target_value)
                        logger.debug("Checked %s (work authorization, from .env)", target_value)
                    except Exception:
                        pass
                continue
            # Sponsorship: "Do you need immigration sponsorship for work permit?" — use WORK_NEED_SPONSORSHIP_ANSWER (Yes/No from .env)
            is_sponsorship = (
                ("sponsorship" in combined_lower and ("visa" in combined_lower or "work" in combined_lower or "employment" in combined_lower) and ("require" in combined_lower or "need" in combined_lower or "future" in combined_lower or "aurez" in combined_lower))
                or ("parrainage" in combined_lower and ("immigration" in combined_lower or "autorisation" in combined_lower or "travail" in combined_lower))
            )
            if is_sponsorship:
                if name:
                    seen_names.add(name)
                want_yes = (WORK_NEED_SPONSORSHIP_ANSWER or "Yes").strip().lower() in ("yes", "oui", "1", "true")
                target_value = "Yes" if want_yes else "No"
                if name:
                    for sel in (f'input[type="radio"][data-test-text-selectable-option__input="{target_value}"][name="{name}"]', f'input[type="radio"][value="{"1" if want_yes else "0"}"][name="{name}"]', f'input[type="radio"][value="{target_value.lower()}"][name="{name}"]', f'input[type="radio"][value="{target_value}"][name="{name}"]'):
                        try:
                            await modal.locator(sel).first.check(timeout=3000)
                            logger.debug("Checked %s (sponsorship question, from .env)", target_value)
                            break
                        except Exception:
                            continue
                else:
                    try:
                        await r.evaluate("""(el, val) => {
                            const container = el.closest('fieldset') || el.closest('[role="group"]') || el.parentElement?.parentElement;
                            const numVal = (val === 'Yes') ? '1' : '0';
                            const input = container?.querySelector('input[data-test-text-selectable-option__input="' + val + '"]') || container?.querySelector('input[type="radio"][value="' + numVal + '"]') || container?.querySelector('input[type="radio"][value="' + val + '"]');
                            if (input) { input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); }
                            else { const lbl = container?.querySelector('[data-test-text-selectable-option__label="' + val + '"]'); if (lbl) lbl.click(); }
                        }""", target_value)
                        logger.debug("Checked %s (sponsorship question, from .env)", target_value)
                    except Exception:
                        pass
                continue
            if name:
                seen_names.add(name)
            option_label = await r.evaluate("el => el.closest('label')?.innerText || el.getAttribute('aria-label') || ''")
            question_text = (group_label or block_text or "").strip()
            full_label = f"{group_label} {option_label}".strip() or (option_label or question_text)
            answer = get_answer_for_question(
                question_text or full_label,
                years_default=EASY_APPLY_YEARS_DEFAULT,
                cv_path=cv_path,
                use_gemini=USE_GEMINI_FOR_CV,
            )
            if answer is None and (question_text or full_label):
                answer = get_answer_any_question_gemini(question_text or full_label)
            if answer is None and group_label:
                gl = group_label.lower()
                if ("sponsorship" in gl or "visa" in gl) and ("require" in gl or "need" in gl or "future" in gl):
                    answer = "Yes"
            # If we still can't determine: default to Yes (user: "if you could not make the right selection just check yes")
            if answer is None:
                answer = "Yes"
            if answer is None:
                continue
            answer_lower = str(answer).strip().lower()
            # For Yes/No: find and check the radio with matching value in this group (works regardless of iteration order)
            if answer_lower in ("yes", "no", "oui", "non"):
                target_value = "Yes" if answer_lower in ("yes", "oui") else "No"
                radio_checked = False
                if name:
                    for sel in (f'input[type="radio"][data-test-text-selectable-option__input="{target_value}"][name="{name}"]', f'input[type="radio"][value="{"1" if target_value == "Yes" else "0"}"][name="{name}"]', f'input[type="radio"][value="{target_value.lower()}"][name="{name}"]', f'input[type="radio"][value="{target_value}"][name="{name}"]'):
                        try:
                            await modal.locator(sel).first.check(timeout=3000)
                            radio_checked = True
                            break
                        except Exception:
                            continue
                if not radio_checked:
                    try:
                        await r.evaluate("""(el, val) => {
                            const container = el.closest('fieldset') || el.closest('[role="group"]') || el.parentElement?.parentElement;
                            const numVal = (val === 'Yes') ? '1' : '0';
                            const input = container?.querySelector('input[data-test-text-selectable-option__input="' + val + '"]') || container?.querySelector('input[type="radio"][value="' + numVal + '"]') || container?.querySelector('input[type="radio"][value="' + val + '"]');
                            if (input) { input.checked = true; input.dispatchEvent(new Event('change', { bubbles: true })); }
                            else { const lbl = container?.querySelector('[data-test-text-selectable-option__label="' + val + '"]'); if (lbl) lbl.click(); }
                        }""", target_value)
                        radio_checked = True
                    except Exception:
                        pass
                if radio_checked:
                    logger.debug("Checked %s for '%s'", target_value, (question_text or full_label)[:60])
                elif not radio_checked:
                    opt_label_lower = (option_label or "").strip().lower()
                    if ("yes" in answer_lower or "oui" in answer_lower) and ("yes" in opt_label_lower or "oui" in opt_label_lower):
                        try:
                            await r.check(timeout=3000)
                            logger.debug("Checked Yes for '%s'", (question_text or full_label)[:60])
                        except Exception as e_radio:
                            logger.debug("Could not check Yes radio: %s", e_radio)
                    elif ("no" in answer_lower or "non" in answer_lower) and ("no" in opt_label_lower or "non" in opt_label_lower):
                        try:
                            await r.check(timeout=3000)
                            logger.debug("Checked No for '%s'", (question_text or full_label)[:60])
                        except Exception as e_radio:
                            logger.debug("Could not check No radio: %s", e_radio)
                    else:
                        logger.debug("Could not check radio %s for '%s'", target_value, (question_text or full_label)[:60])
            else:
                opt_label_lower = (option_label or "").strip().lower()
                if answer_lower in opt_label_lower or (opt_label_lower and opt_label_lower in answer_lower):
                    await r.check(timeout=3000)
                    logger.debug("Checked '%s' for '%s'", answer, (question_text or full_label)[:60])
        except Exception as e:
            logger.debug("Fill radio/checkbox: %s", e)


async def _click_post_submit_confirmation(page: Page) -> None:
    """After Soumettre, click OK/Fermer/Done so the success overlay closes and next job is clickable."""
    await asyncio.sleep(0.6)
    try:
        confirm = page.locator(CONFIRMATION_BUTTON).first
        await confirm.wait_for(state="visible", timeout=5000)
        await confirm.click(timeout=5000)
        logger.debug("Clicked post-submit confirmation (OK/Fermer).")
    except Exception as e:
        logger.debug("No post-submit confirmation button or already closed: %s", e)


async def fill_contact_and_click_suivant(page: Page, preferred_email: str = "") -> bool:
    """
    Easy Apply modal: contact step (email), then each step fill Additional Questions (years=3)
    and click Suivant / Vérifier / Soumettre.
    """
    modal = page.locator(EASY_APPLY_MODAL).first
    try:
        await modal.wait_for(state="visible", timeout=15000)
    except Exception as e:
        logger.warning("Easy Apply modal did not appear: %s", e)
        return False

    # Contact step: leave the default email as-is (do nothing)

    # If "Envoyer la candidature" / Send application is already visible (one-step apply), click it after a short fill
    await asyncio.sleep(0.5)
    if await _click_submit_if_visible(modal, page):
        return True

    # Click Suivant on first step
    try:
        next_btn = modal.locator(NEXT_BUTTON).first
        await next_btn.click(timeout=10000)
        logger.info("Clicked Suivant (contact step).")
    except Exception as e:
        logger.warning("Could not click Suivant: %s", e)
        return False

    # Subsequent steps: fill Additional Questions (years etc.), then Vérifier / Suivant / Soumettre
    for _ in range(12):
        await asyncio.sleep(0.8)
        await _fill_additional_questions(modal)
        await asyncio.sleep(0.3)
        # If validation errors are visible (e.g. "Enter a decimal number larger than 0.0"), skip this job and close without saving
        if await _modal_has_validation_errors(modal):
            logger.warning("Validation errors in form — closing modal and skipping this offer (not saving).")
            await close_easy_apply_modal(page)
            return False
        if await _click_submit_if_visible(modal, page):
            return True
        verify_btn = modal.locator(VERIFY_BUTTON).first
        if await verify_btn.is_visible():
            await verify_btn.click(timeout=10000)
            logger.info("Clicked Vérifier.")
            continue
        next_btn = modal.locator(NEXT_BUTTON).first
        if await next_btn.is_visible():
            await next_btn.click(timeout=10000)
            logger.info("Clicked Suivant.")
        else:
            break
    return True


async def _click_submit_if_visible(modal, page: Page) -> bool:
    """Click 'Envoyer la candidature' / Send application / Soumettre if visible (modal or page). Returns True if clicked."""
    for selector in SUBMIT_BUTTON_SELECTORS:
        try:
            # Try inside modal first
            btn = modal.locator(selector).first
            if await btn.is_visible():
                await btn.scroll_into_view_if_needed(timeout=3000)
                await btn.click(timeout=10000)
                logger.info("Clicked Envoyer la candidature / Submit — application sent.")
                await _click_post_submit_confirmation(page)
                await wait_for_easy_apply_modal_closed(page, timeout_ms=10000)
                return True
        except Exception:
            pass
    for selector in SUBMIT_BUTTON_SELECTORS:
        try:
            # Try on whole page (button may be outside modal container)
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.scroll_into_view_if_needed(timeout=3000)
                await btn.click(timeout=10000)
                logger.info("Clicked Envoyer la candidature / Submit — application sent.")
                await _click_post_submit_confirmation(page)
                await wait_for_easy_apply_modal_closed(page, timeout_ms=10000)
                return True
        except Exception:
            pass
    return False


async def _modal_has_validation_errors(modal) -> bool:
    """True if the modal shows validation error text (e.g. 'Enter a decimal number larger than 0.0')."""
    try:
        body_text = (await modal.evaluate("el => (el?.innerText || '').toLowerCase()")) or ""
        for phrase in VALIDATION_ERROR_PHRASES:
            if phrase in body_text:
                return True
        invalid = await modal.locator("[aria-invalid='true']").count()
        if invalid > 0:
            return True
    except Exception:
        pass
    return False


async def _click_discard_if_save_dialog_visible(page: Page) -> bool:
    """If 'Save this application?' / 'Enregistrer cette candidature?' dialog is visible, click Supprimer/Discard. Returns True if clicked."""
    for selector in DISCARD_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click(timeout=5000)
                logger.info("Clicked Supprimer/Discard (did not save application).")
                await asyncio.sleep(0.5)
                return True
        except Exception:
            continue
    return False


async def close_easy_apply_modal(page: Page) -> None:
    """Close the Easy Apply modal without saving (e.g. after skip or validation error). Clicks Supprimer/Discard if 'Save?' dialog appears."""
    try:
        # If "Save this application?" dialog is already open, click Supprimer/Discard first (FR + EN)
        await _click_discard_if_save_dialog_visible(page)
        await asyncio.sleep(0.3)
        # Try modal dismiss / X button
        for selector in [
            ".artdeco-modal__dismiss",
            "button[aria-label*='Fermer']",
            "button[aria-label*='Close']",
            "[data-test-modal] button[aria-label*='Fermer']",
            "[data-test-modal] button[aria-label*='Close']",
            CLOSE_BUTTON,
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click(timeout=5000)
                    logger.info("Closed Easy Apply modal (did not save).")
                    await asyncio.sleep(0.5)
                    # After X, "Save this application?" may appear — click Supprimer/Discard
                    await _click_discard_if_save_dialog_visible(page)
                    return
            except Exception:
                continue
    except Exception as e:
        logger.debug("Close modal: %s", e)


async def wait_for_easy_apply_modal_closed(page: Page, timeout_ms: int = 12000) -> None:
    """Wait until the Easy Apply modal is fully closed so the next job card can be clicked (no intercept)."""
    timeout_sec = min(15, max(5, timeout_ms / 1000.0))
    # If "Save this application?" dialog is visible, click Supprimer/Discard first
    await _click_discard_if_save_dialog_visible(page)
    await asyncio.sleep(0.2)
    # Click Terminé/OK repeatedly until confirmation button is gone (success overlay closes)
    for _ in range(6):
        try:
            confirm = page.locator(CONFIRMATION_BUTTON).first
            if await confirm.is_visible():
                await confirm.click(timeout=5000)
                await asyncio.sleep(0.6)
            else:
                break
        except Exception:
            break
    # Wait for any modal/overlay in the outlet to be hidden
    for selector in [
        ".artdeco-modal-overlay",
        "#artdeco-modal-outlet .artdeco-modal-overlay",
        "[data-test-modal]",
        EASY_APPLY_MODAL_ID,
    ]:
        try:
            await page.wait_for_selector(selector, state="hidden", timeout=timeout_sec)
        except Exception:
            pass
    try:
        overlay = page.locator("#artdeco-modal-outlet .artdeco-modal-overlay, #artdeco-modal-outlet [role='dialog']")
        await overlay.first.wait_for(state="hidden", timeout=int(timeout_sec))
    except Exception:
        pass
    await asyncio.sleep(0.6)


async def run_easy_apply_flow(
    page: Page, form_answers: Dict[str, Any], resume_path: str = ""
) -> bool:
    """
    After Easy Apply button was clicked: fill form and submit.
    Uses form_answers to match questions; uploads resume if path provided.
    """
    path = resume_path or RESUME_PATH
    try:
        return await fill_easy_apply_form(page, form_answers, path)
    except Exception as e:
        logger.exception("Easy Apply flow failed: %s", e)
        await close_easy_apply_modal(page)
        return False
