"""Exact B2_o1 prompt rendering and strict continuous-probability contract."""
import json
import re
PREDICTION_PROMPT_VERSION = "b2_o1-reasons-v2"
import hashlib
import math
import os
from pathlib import Path

DEFAULT_PROMPT = Path(__file__).with_name("prompt_b2_o1.txt")

def prompt_reference():
    path = Path(os.getenv("B2_O1_PROMPT_PATH") or str(DEFAULT_PROMPT))
    if not path.is_file():
        return {"available": False, "message_role": "user", "name": "B2_o1"}
    data = path.read_bytes()
    return {"available": True, "message_role": "user", "name": "B2_o1",
            "sha256": hashlib.sha256(data).hexdigest()}

def validate_future_probability(value):
    if not isinstance(value, dict) or set(value) != {"flaky_probability"}:
        raise ValueError("Expected exactly flaky_probability.")
    probability = value["flaky_probability"]
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise ValueError("Probability must be a number, not a label or string.")
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("Probability must be finite and between 0 and 1.")
    return {"flaky_probability": float(probability)}


def render_prediction_prompt(payload, expected_template_hash=None):
    allowed = {"test_code", "failure_reports", "project_change_description"}
    if not isinstance(payload, dict) or set(payload) - allowed or not {"test_code", "failure_reports"} <= set(payload):
        raise ValueError("Saved evidence does not match the B2_o1 input contract.")
    if not isinstance(payload["test_code"], str) or not payload["test_code"].strip():
        raise ValueError("Saved test source is missing.")
    if not isinstance(payload["failure_reports"], list) or not payload["failure_reports"]:
        raise ValueError("Saved failure reports are missing.")
    from .evidence import B1_FIELDS
    for report in payload["failure_reports"]:
        if not isinstance(report, dict) or not report or set(report) - set(B1_FIELDS) or any(not isinstance(v, str) for v in report.values()):
            raise ValueError("Saved failure reports do not match the B1 research contract.")
    if "project_change_description" in payload and not isinstance(payload["project_change_description"], str):
        raise ValueError("Saved change description must be a string.")
    path = Path(os.getenv("B2_O1_PROMPT_PATH") or str(DEFAULT_PROMPT))
    try:
        raw = path.read_bytes()
    except OSError:
        raise ValueError("The original B2_o1 prompt is unavailable. Ask the administrator to configure B2_O1_PROMPT_PATH.") from None
    digest = hashlib.sha256(raw).hexdigest()
    if expected_template_hash and digest != expected_template_hash:
        raise ValueError("The research prompt changed after this evidence was saved. Restore its original version.")
    template = raw.decode("utf-8-sig")
    if template.count("{{TARGET_B2_O1_JSON}}") != 1 or template.count("LABELED EXAMPLE ") != 2:
        raise ValueError("The B2_o1 prompt must contain its target placeholder and two fixed research examples.")
    output_heading = re.search(r"(?m)^OUTPUT REQUIREMENTS\r?$", template)
    if not output_heading:
        raise ValueError("The research prompt is missing its output requirements section.")
    output_rules = Path(__file__).with_name("prediction_output.txt").read_text(encoding="utf-8")
    template = template[:output_heading.start()] + output_rules
    effective_hash = hashlib.sha256(template.encode("utf-8")).hexdigest()
    rendered = template.replace("{{TARGET_B2_O1_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2), 1)
    if len(rendered) > 180_000:
        raise ValueError("The complete B2_o1 prompt exceeds the supported input limit.")
    return rendered, effective_hash

def validate_prediction_response(value):
    if not isinstance(value, dict) or set(value) != {"flaky_probability", "reasons"}:
        raise ValueError("Expected flaky_probability and reasons.")
    probability = validate_future_probability({"flaky_probability": value["flaky_probability"]})
    reasons = value["reasons"]
    if not isinstance(reasons, list) or not 2 <= len(reasons) <= 4:
        raise ValueError("Expected two to four evidence-based reasons.")
    if any(not isinstance(reason, str) or not reason.strip() or len(reason) > 500 for reason in reasons):
        raise ValueError("Each reason must be a nonempty string of at most 500 characters.")
    return {**probability, "reasons": [reason.strip() for reason in reasons]}
