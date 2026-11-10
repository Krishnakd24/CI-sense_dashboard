import pytest
from app.services.xml_parser import parse_report
from app.services.java_methods import extract_method_code
def test_preserves_duplicate_failures_and_values():
    xml=b'<testsuites xmlns="urn:junit"><testsuite><testcase name="a" classname="p.T"><failure type="Error" message="expected:&lt;1&gt; but was:&lt;2&gt;">at p.T.a(T.java:9)</failure><system-out>hello</system-out></testcase><testcase name="a" classname="p.T"><error>bad</error></testcase><testcase name="pass"/></testsuite></testsuites>'
    rows=parse_report(xml)
    assert len(rows)==2
    assert rows[0]["expected_value"]=="1" and rows[0]["actual_value"]=="2"
    assert rows[0]["line_number"]==9 and rows[0]["test_stdout"]=="hello"
    assert rows[1]["execution_result"]=="ERROR"
def test_forbids_entities():
    with pytest.raises(Exception):
        parse_report(b'<!DOCTYPE testsuite [<!ENTITY x SYSTEM "file:///etc/passwd">]><testsuite><testcase><failure>&x;</failure></testcase></testsuite>')
@pytest.mark.parametrize("xml",[b"",b"<html/>",b"<testsuite/>",b"<broken",b"x"*5242881])
def test_invalid_reports(xml):
    with pytest.raises(Exception): parse_report(xml)
def test_original_java_extractor_ignores_string_braces():
    text='public void example() { String s = "}"; /* } */ assertTrue(true); }'
    assert extract_method_code(text,"example")==text
def test_overloaded_methods_are_not_guessed():
    assert extract_method_code('public void x() {}\npublic void x(int a) {}',"x") is None
