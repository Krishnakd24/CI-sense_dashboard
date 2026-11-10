import json
from pathlib import Path
import pytest
from app.services.evidence import failure_reports, group_failures, assemble, payload_hash
from app.services.xml_parser import parse_report
from app.services.research_contract import validate_future_probability, prompt_reference

def test_b1_projection_preserves_strings_and_omits_identity():
    raw = {"test_name":"privateName","test_class":"SecretProject.Test","line_number":0,
           "duration_seconds":"0.005","failure_message":"NA","stack_trace":"line 1\nline 2",
           "expected_value":"","test_stdout":None,"execution_result":"FAIL"}
    assert failure_reports(raw) == [{"execution_result":"FAIL","stack_trace":"line 1\nline 2",
                                     "line_number":"0","duration_seconds":"0.005"}]

def test_duplicate_entries_group_only_within_same_suite():
    raw=b'<testsuites><testsuite><testcase classname="p.T" name="x"><failure message="one"/></testcase><testcase classname="p.T" name="x"><error message="two"/></testcase></testsuite><testsuite><testcase classname="p.T" name="x"><failure message="three"/></testcase></testsuite></testsuites>'
    groups=group_failures(parse_report(raw))
    assert len(groups)==2
    assert len(groups[0]["entries"])==2
    assert failure_reports(groups[0])==[
        {"execution_result":"FAIL","failure_message":"one"},
        {"execution_result":"ERROR","error_message":"two"}]

def ready_inputs():
    return ({"test_name":"x","test_class":"p.T","execution_result":"FAIL"},
            {"status":"complete","scope":"method","code":"void x() {}","commit":"a"*40},
            {"status":"complete","commit":"a"*40,
             "summary":{"project_change_description":"Changes a condition."}})

def test_final_payload_exact_contract():
    raw,source,diff=ready_inputs()
    payload,issues=assemble(raw,source,diff)
    assert not issues
    assert payload=={"test_code":"void x() {}","failure_reports":[{"execution_result":"FAIL"}],
                     "project_change_description":"Changes a condition."}
    assert payload_hash(payload)==payload_hash(json.loads(json.dumps(payload)))

@pytest.mark.parametrize("change",["full_file","wrong_commit","failed_diff","missing_source"])
def test_no_silent_substitution_or_missing_component(change):
    raw,source,diff=ready_inputs()
    if change=="full_file":source["scope"]="full file"
    if change=="wrong_commit":source["commit"]="b"*40
    if change=="failed_diff":diff["status"]="failed"
    if change=="missing_source":source["status"]="missing"
    payload,issues=assemble(raw,source,diff)
    assert payload is None and issues

@pytest.mark.parametrize("value",[True,"0.5",-0.1,1.1,float("nan"),float("inf")])
def test_future_probability_rejects_labels_and_invalid_numbers(value):
    with pytest.raises(ValueError):validate_future_probability({"flaky_probability":value})
def test_future_probability_is_continuous():
    assert validate_future_probability({"flaky_probability":0.731})=={"flaky_probability":0.731}
    with pytest.raises(ValueError):validate_future_probability({"flaky_probability":0.4,"diagnosis":"extra"})

def test_local_research_projection_matches_all_available_b1_rows():
    path=Path(__file__).resolve().parents[3]/"Final_data"/"b1_data_v1.json"
    if not path.exists():pytest.skip("Local research data is intentionally not bundled.")
    for record in json.loads(path.read_text(encoding="utf-8-sig")):
        assert failure_reports({"entries":record["failure_reports"]})==record["failure_reports"]
