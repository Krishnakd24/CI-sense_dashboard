from app.main import app,current_user
from app.db import Session,User,ModelConfig,Analysis,TestEvidence
from app.settings import cipher
from app.services.llm import ModelFailure
XML=b'<testsuite><testcase classname="p.T" name="fails"><failure type="AssertionError">trace</failure></testcase></testsuite>'
def upload(client):
    r=client.post("/analyses",data={"commit":"abcdef1","admin_test":"true","repository_url":"https://github.com/example/repo"},files={"report":("report.xml",XML,"application/xml")})
    assert r.status_code==200,r.text
    return r.json()["id"]
def configs():
    with Session() as db:
        for role in ("diff",): db.add(ModelConfig(role=role,provider="openai",base_url="https://api.openai.com/v1",model="test-model",encrypted_key=cipher().encrypt(b"never-return-this").decode()))
        db.commit()
def test_upload_persist_and_delete(client):
    aid=upload(client)
    a=client.get("/analyses/"+aid).json()
    assert a["status"]=="draft" and len(a["tests"])==1
    assert client.get("/analyses?admin_test=true").json()[0]["id"]==aid
    assert client.delete("/analyses/"+aid).status_code==200
    assert client.get("/analyses/"+aid).status_code==404
def test_owner_and_admin_checks(client):
    aid=upload(client)
    def other():
        with Session() as db:return db.get(User,"2")
    app.dependency_overrides[current_user]=other
    assert client.get("/analyses/"+aid).status_code==404
    assert client.delete("/analyses/"+aid).status_code==404
    assert client.get("/admin/models").status_code==403
    assert client.get("/analyses?admin_test=true").status_code==403
def test_csrf(client):
    assert client.post("/auth/logout",headers={"Origin":"https://evil.example"}).status_code==403
def test_keys_are_not_returned(client):
    configs()
    response=client.get("/admin/models")
    assert "never-return-this" not in response.text and "encrypted_key" not in response.text
    assert response.json()[0]["key_configured"] is True
    assert client.post("/admin/models/classifier/test").status_code==400
def test_no_config_no_extraction(client):
    aid=upload(client); tid=client.get("/analyses/"+aid).json()["tests"][0]["id"]
    assert client.post("/analyses/"+aid+"/extract",json={"test_ids":[tid]}).status_code==409
def test_complete_pipeline_persists_without_classifier(client,monkeypatch):
    configs()
    from app import pipeline
    calls=[]
    class FakeGitHub:
        def __init__(self,*args):pass
        async def authorize(self,*args):return {"id":123,"private":False,"full_name":"example/repo"}
        async def resolve_commit(self,*args):return {"commit":"a"*40,"parent":"b"*40}
        async def diff(self,*args):return {"status":"complete","commit":"a"*40,"parent":"b"*40,"files":[]}
        async def tree(self,*args):return ["p/T.java"]
        async def source(self,*args):return {"status":"complete","path":"p/T.java","code":"void fails() {}","scope":"method","commit":"a"*40}
        async def close(self):pass
    async def fake_invoke(config,purpose,evidence):
        calls.append(purpose)
        return {"project_change_description":"No changes."}
    monkeypatch.setattr(pipeline,"GitHub",FakeGitHub);monkeypatch.setattr(pipeline,"invoke",fake_invoke)
    aid=upload(client);tid=client.get("/analyses/"+aid).json()["tests"][0]["id"]
    assert client.post("/analyses/"+aid+"/extract",json={"test_ids":[tid]}).status_code==202
    saved=client.get("/analyses/"+aid).json()
    assert saved["status"]=="complete" and saved["tests"][0]["source"]["path"]=="p/T.java"
    assert calls==["diff"]
    assert set(saved["tests"][0]["payload"])=={"test_code","failure_reports","project_change_description"}
    assert client.get("/analyses/"+aid+"/tests/"+tid+"/payload").json()==saved["tests"][0]["payload"]
    assert client.get("/analyses/"+aid+"/approved-evidence").status_code==200
    assert client.post("/analyses/"+aid+"/extract",json={"test_ids":[tid]}).status_code==409
def test_model_failure_is_persisted(client,monkeypatch):
    configs()
    from app import pipeline
    class FakeGitHub:
        def __init__(self,*args):pass
        async def authorize(self,*args):return {"id":123,"private":False,"full_name":"example/repo"}
        async def resolve_commit(self,*args):return {"commit":"a"*40,"parent":"b"*40}
        async def diff(self,*args):return {"status":"complete","commit":"a"*40,"parent":"b"*40,"files":[]}
        async def close(self):pass
    async def fail(*args):raise ModelFailure("Provider returned HTTP 401.")
    monkeypatch.setattr(pipeline,"GitHub",FakeGitHub);monkeypatch.setattr(pipeline,"invoke",fail)
    aid=upload(client);tid=client.get("/analyses/"+aid).json()["tests"][0]["id"]
    client.post("/analyses/"+aid+"/extract",json={"test_ids":[tid]})
    a=client.get("/analyses/"+aid).json()
    assert a["status"]=="failed"
    assert a["message"]=="Analysis could not be completed. Please contact the administrator."
    assert a["diff"]["status"]=="failed" and "401" in a["technical_error"]
