"""Adapted from failing_logs_XMLS/extract_test_failure_details.ps1.
Preserves namespace, exception, trace, assertion and stdout extraction rules.
Research CSV joins are replaced by independently preserved testcase entries.
"""
import re
from defusedxml.ElementTree import fromstring
MAX_XML = 5 * 1024 * 1024
def parse_report(data: bytes):
    if not data or len(data) > MAX_XML: raise ValueError("Upload an XML report between 1 byte and 5 MB.")
    root = fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    local = lambda node: node.tag.rsplit("}", 1)[-1]
    if local(root) not in ("testsuite", "testsuites"): raise ValueError("Expected a JUnit testsuite or testsuites root.")
    parents = {child: parent for parent in root.iter() for child in parent}
    suites = {node: index for index, node in enumerate(root.iter()) if local(node) == "testsuite"}
    result = []
    for case in root.iter():
        if local(case) != "testcase": continue
        failures = [n for n in case if local(n) == "failure"]
        errors = [n for n in case if local(n) == "error"]
        if not failures and not errors: continue
        problems = failures + errors
        text = lambda nodes: "\n".join(n.get("message", "") for n in nodes)
        stack = "\n--- additional failure ---\n".join("".join(n.itertext()) for n in problems)
        exception = "; ".join(dict.fromkeys(n.get("type") for n in problems if n.get("type")))
        fallback = re.search(r"(?m)^\s*([\w.$]+(?:Exception|Error|Failure))(?::|\s|$)", stack)
        if not exception and fallback: exception = fallback[1]
        location = re.search(r"\(([\w.$-]+\.(?:java|kt|scala|groovy)):(\d+)\)", stack)
        assertion = text(failures) + "\n" + text(errors) + "\n" + stack
        values = re.search(r"expected\s*:?\s*<([^\r\n]*?)>\s*but\s*(?:was|actual)\s*:?\s*<([^\r\n]*?)>", assertion, re.I | re.S)
        suite = parents.get(case)
        result.append(dict(suite_index=suites.get(suite), suite_name=suite.get("name", "") if suite is not None else "", test_name=case.get("name", ""), test_class=case.get("classname", ""),
            execution_result="ERROR" if errors else "FAIL", failure_message=text(failures),
            error_message=text(errors), exception_type=exception, stack_trace=stack,
            source_file=location[1] if location else None, line_number=int(location[2]) if location else None,
            expected_value=values[1] if values else None, actual_value=values[2] if values else None,
            duration_seconds=case.get("time"), test_stdout="\n".join("".join(n.itertext()) for n in case if local(n) == "system-out"),
            test_stderr="\n".join("".join(n.itertext()) for n in case if local(n) == "system-err"),
            original_testcase_attributes=dict(case.attrib),
            problems=[dict(kind=local(n), attributes=dict(n.attrib), content="".join(n.itertext())) for n in problems]))
        if len(result) > 200: raise ValueError("Reports may contain at most 200 failing testcase entries.")
    if not result: raise ValueError("No failing tests were found in this report.")
    return result
