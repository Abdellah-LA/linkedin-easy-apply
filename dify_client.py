"""
Dify integration: call the workflow with job text and get apply_status + form_answers.
"""
import json
import time
from typing import Any, Dict, Optional

import requests

from config import DIFY_API_KEY, DIFY_BASE_URL, DIFY_CV_FILE_ID, DIFY_USER
from logger_config import logger

WORKFLOW_RUN_URL = "/workflows/run"
WORKFLOW_RUN_DETAIL_URL = "/workflows/run/{workflow_run_id}"


def call_dify_brain(job_text: str) -> Dict[str, Any]:
    """
    Send job text to Dify workflow and wait for result.
    Payload: {"inputs": {"linkedin_data": job_text, "cv_pdf": "YOUR_CV_FILE_ID"}, "user": "abdellah_bot"}
    Returns parsed JSON with apply_status (PROCEED | SKIP) and form_answers (e.g. years of experience).
    """
    if not DIFY_API_KEY or not DIFY_BASE_URL:
        logger.error("DIFY_API_KEY or DIFY_BASE_URL not set")
        return {"apply_status": "SKIP", "form_answers": {}, "error": "Missing Dify config"}

    url = f"{DIFY_BASE_URL}{WORKFLOW_RUN_URL}"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {
            "linkedin_data": job_text,
            "cv_pdf": DIFY_CV_FILE_ID or "",
        },
        "user": DIFY_USER,
        "response_mode": "blocking",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.exception("Dify workflow request failed: %s", e)
        return {"apply_status": "SKIP", "form_answers": {}, "error": str(e)}
    except json.JSONDecodeError as e:
        logger.exception("Dify response not JSON: %s", e)
        return {"apply_status": "SKIP", "form_answers": {}, "error": str(e)}

    # Blocking mode: response may have data.outputs or we need to poll run detail
    workflow_data = data.get("data") or data
    status = workflow_data.get("status")
    outputs = workflow_data.get("outputs") or {}

    if status == "succeeded":
        apply_status = (outputs.get("apply_status") or "SKIP").strip().upper()
        if apply_status not in ("PROCEED", "SKIP"):
            apply_status = "SKIP"
        form_answers = outputs.get("form_answers")
        if form_answers is None:
            form_answers = {}
        if isinstance(form_answers, str):
            try:
                form_answers = json.loads(form_answers)
            except json.JSONDecodeError:
                form_answers = {}
        return {"apply_status": apply_status, "form_answers": form_answers or {}}

    # If blocking returned "running", poll for completion
    task_id = data.get("task_id") or data.get("workflow_run_id")
    if task_id and status == "running":
        detail_url = f"{DIFY_BASE_URL}{WORKFLOW_RUN_DETAIL_URL.format(workflow_run_id=task_id)}"
        for _ in range(60):
            time.sleep(2)
            try:
                r = requests.get(detail_url, headers=headers, timeout=30)
                r.raise_for_status()
                detail = r.json()
            except Exception as e:
                logger.warning("Poll run detail failed: %s", e)
                continue
            st = detail.get("status")
            if st == "succeeded":
                outputs = detail.get("outputs") or {}
                apply_status = (outputs.get("apply_status") or "SKIP").strip().upper()
                if apply_status not in ("PROCEED", "SKIP"):
                    apply_status = "SKIP"
                form_answers = outputs.get("form_answers") or {}
                if isinstance(form_answers, str):
                    try:
                        form_answers = json.loads(form_answers)
                    except json.JSONDecodeError:
                        form_answers = {}
                return {"apply_status": apply_status, "form_answers": form_answers}
            if st in ("failed", "stopped"):
                return {"apply_status": "SKIP", "form_answers": {}, "error": detail.get("error", st)}

    return {"apply_status": "SKIP", "form_answers": {}, "error": f"Workflow status: {status}"}
