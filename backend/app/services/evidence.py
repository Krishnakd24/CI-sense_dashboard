"""Research-compatible evidence projection; application metadata never enters targets."""
import hashlib
import json

B1_FIELDS = (
    "execution_result", "exception_type", "failure_message", "error_message",
    "stack_trace", "source_file", "line_number", "expected_value", "actual_value",
    "duration_seconds", "test_stdout", "test_stderr",
)
SCHEMA_VERSION = "b2_o1-v1"

def failure_reports(raw):
    entries = raw.get("entries", [raw])
    return [{key: str(entry[key]) for key in B1_FIELDS
             if entry.get(key) is not None and entry[key] not in ("", "NA")}
            for entry in entries]

def group_failures(entries):
    """Group exact identities within one suite, preserving all report entries in order."""
    groups = {}
    for index, entry in enumerate(entries):
        key = (entry.get("suite_index"), entry["test_class"], entry["test_name"])
        if not entry["test_class"] or not entry["test_name"]:
            key = ("unresolved", index)
        if key not in groups:
            groups[key] = {**entry, "entries": [], "entry_indexes": []}
        groups[key]["entries"].append(entry)
        groups[key]["entry_indexes"].append(index)
    return list(groups.values())

def assemble(raw, source, diff):
    issues = []
    if not raw.get("test_class") or not raw.get("test_name"):
        issues.append("XML testcase classname and name are required for exact source resolution.")
    if source.get("status") != "complete" or source.get("scope") != "method" or not source.get("code"):
        issues.append("An unambiguous test method at the selected commit is required.")
    if source.get("commit") != diff.get("commit"):
        issues.append("Source and diff must refer to the same selected commit.")
    summary = diff.get("summary", {})
    description = summary.get("project_change_description")
    if diff.get("status") != "complete" or not isinstance(description, str) or not description.strip():
        issues.append("A complete diff and grounded project change description are required.")
    if any(not report for report in failure_reports(raw)):
        issues.append("Every report entry must contain failure evidence.")
    if issues:
        return None, issues
    payload = {
        "test_code": source["code"],
        "failure_reports": failure_reports(raw),
        "project_change_description": description,
    }
    return payload, []

def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
