import pytest
from app.services.research_contract import validate_prediction_response, render_prediction_prompt
from test_prediction import prepare

def test_reasons_are_validated_and_retained():
    result=validate_prediction_response({"flaky_probability":0.731,"reasons":[" Timing-dependent assertion. ","Missing helper code limits certainty."]})
    assert result["flaky_probability"]==0.731
    assert result["reasons"]==["Timing-dependent assertion.","Missing helper code limits certainty."]

@pytest.mark.parametrize("reasons",[None,[],["one"],["one"]*5,["one"," "],["one",2],["one","x"*501]])
def test_invalid_reasons_rejected(reasons):
    with pytest.raises(ValueError):
        validate_prediction_response({"flaky_probability":0.4,"reasons":reasons})

def test_old_probability_only_result_not_accepted_for_new_calls():
    with pytest.raises(ValueError):
        validate_prediction_response({"flaky_probability":0.4})

def test_new_output_rules_replace_old_without_changing_research_file(client,tmp_path,monkeypatch):
    _,_,payload=prepare(client,tmp_path,monkeypatch)
    path=tmp_path/"prompt.txt"
    original=path.read_bytes()
    rendered,digest=render_prediction_prompt(payload)
    assert path.read_bytes()==original
    assert 'Provide 2-4 short reasons' in rendered
    assert rendered.count("OUTPUT REQUIREMENTS")==1
    assert rendered.count("LABELED EXAMPLE ")==2
    assert "Return probability only" not in rendered
