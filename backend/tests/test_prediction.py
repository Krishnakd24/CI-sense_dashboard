import asyncio
import json
import pytest
import httpx
from types import SimpleNamespace
from app.db import Session, Analysis, TestEvidence, EvidencePayload, ModelConfig, Prediction, ComponentOutput, User
from app.settings import cipher
from app.services.evidence import payload_hash
from app.services.research_contract import render_prediction_prompt
from app.services.llm import ModelFailure
from app.main import app, current_user

def prepare(client, tmp_path, monkeypatch):
    prompt=tmp_path/"prompt.txt"
    prompt.write_text("Instructions\nLABELED EXAMPLE 1\nexample one\nLABELED EXAMPLE 2\nexample two\nTARGET\n{{TARGET_B2_O1_JSON}}\nOUTPUT REQUIREMENTS\nReturn probability only",encoding="utf-8")
    monkeypatch.setenv("B2_O1_PROMPT_PATH",str(prompt))
    payload={"test_code":"void fails() {}","failure_reports":[{"execution_result":"FAIL"}],
             "project_change_description":"Changes a condition."}
    with Session() as db:
        a=Analysis(owner_id="1",repository="example/repo",commit="a"*40,admin_test=True,status="complete",artifact_key="test/report.xml")
        db.add(a);db.flush()
        t=TestEvidence(analysis_id=a.id,name="T#fails",selected=True,xml={"test_name":"fails","test_class":"T"},source={})
        db.add(t);db.flush()
        p=EvidencePayload(test_id=t.id,schema_version="b2_o1-v1",version=1,payload=payload,sha256=payload_hash(payload),prompt_reference={})
        db.add(p)
        db.add(ModelConfig(role="classifier",provider="openai",base_url="https://api.openai.com/v1",model="test-model",encrypted_key=cipher().encrypt(b"test-key").decode()))
        db.commit()
        return a.id,t.id,payload

def test_prediction_persists_probability_and_prevents_duplicates(client,tmp_path,monkeypatch):
    from app import prediction
    aid,tid,payload=prepare(client,tmp_path,monkeypatch)
    calls=[]
    async def fake(config,purpose,prompt):
        calls.append((purpose,prompt))
        assert purpose=="prediction"
        assert json.dumps(payload,ensure_ascii=False,indent=2) in prompt
        return {"flaky_probability":0.731,"reasons":["Timing-dependent assertion.","Missing helper code limits certainty."]}
    monkeypatch.setattr(prediction,"invoke",fake)
    url=f"/analyses/{aid}/tests/{tid}/predict"
    assert client.post(url).status_code==202
    saved=client.get("/analyses/"+aid).json()["tests"][0]["prediction"]
    assert saved["status"]=="complete" and saved["flaky_probability"]==0.731
    assert len(saved["reasons"])==2
    assert client.post(url).status_code==409
    assert len(calls)==1
    with Session() as db:assert db.query(Prediction).count()==1

def test_failure_saved_without_probability(client,tmp_path,monkeypatch):
    from app import prediction
    aid,tid,_=prepare(client,tmp_path,monkeypatch)
    async def fail(*args):raise ModelFailure("Provider returned HTTP 401.")
    monkeypatch.setattr(prediction,"invoke",fail)
    assert client.post(f"/analyses/{aid}/tests/{tid}/predict").status_code==202
    result=client.get("/analyses/"+aid).json()["tests"][0]["prediction"]
    assert result["status"]=="failed" and "401" in result["technical_error"]
    assert "flaky_probability" not in result
    with Session() as db:assert db.query(Prediction).count()==0

def test_central_connection_is_enabled(client,tmp_path,monkeypatch):
    from app import main
    prepare(client,tmp_path,monkeypatch)
    async def connect(config,purpose):
        assert config.role=="classifier" and purpose=="connection"
        return {"ok":True}
    monkeypatch.setattr(main,"invoke",connect)
    assert client.post("/admin/models/classifier/test").json()=={"ok":True}

def test_other_user_cannot_predict(client,tmp_path,monkeypatch):
    aid,tid,_=prepare(client,tmp_path,monkeypatch)
    def other():
        with Session() as db:return db.get(User,"2")
    app.dependency_overrides[current_user]=other
    assert client.post(f"/analyses/{aid}/tests/{tid}/predict").status_code==404

def test_prompt_hash_mismatch_does_not_call_model(client,tmp_path,monkeypatch):
    _,_,payload=prepare(client,tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="changed"):
        render_prediction_prompt(payload,"wrong-hash")

@pytest.mark.parametrize("provider",["openai","anthropic"])
def test_classifier_sends_user_prompt_and_continuous_output(monkeypatch,provider):
    from app.services import llm
    real_client=httpx.AsyncClient
    async def allow(url):return url
    monkeypatch.setattr(llm,"validate_endpoint",allow)
    def handler(request):
        body=json.loads(request.content)
        assert body["messages"]==[{"role":"user","content":"original research prompt"}]
        assert "system" not in body
        content='{"flaky_probability":0.731,"reasons":["Timing-dependent assertion.","Missing helper code limits certainty."]}'
        data={"content":[{"type":"text","text":content}]} if provider=="anthropic" else {"choices":[{"message":{"content":content}}]}
        return httpx.Response(200,json=data)
    monkeypatch.setattr(llm.httpx,"AsyncClient",lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    config=SimpleNamespace(provider=provider,base_url="https://api.example.com/v1",model="test",encrypted_key=cipher().encrypt(b"test-key").decode())
    assert asyncio.run(llm.invoke(config,"prediction","original research prompt"))=={"flaky_probability":0.731,"reasons":["Timing-dependent assertion.","Missing helper code limits certainty."]}
