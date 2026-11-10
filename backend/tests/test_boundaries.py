from app.main import app,current_user
from app.db import Session,ModelConfig
from app.settings import cipher
def test_unauthenticated_access_is_rejected(client):
    app.dependency_overrides.pop(current_user)
    assert client.get("/projects").status_code==401
    assert client.get("/admin/models").status_code==401
def test_request_limits_apply_before_upload_parser(client):
    response=client.post("/analyses",content=b"x"*(6*1024*1024+1),headers={"Content-Type":"application/xml"})
    assert response.status_code==413
def test_validation_errors_do_not_echo_api_keys(client):
    secret="private-test-value"
    response=client.put("/admin/models/xml",json={"provider":"unsupported","base_url":"https://api.openai.com/v1","model":"model","api_key":secret})
    assert response.status_code==422
    assert secret not in response.text
def test_preserved_keys_are_encrypted(client):
    with Session() as db:
        db.add(ModelConfig(role="xml",provider="openai",base_url="https://api.openai.com/v1",model="test",encrypted_key=cipher().encrypt(b"private-test-value").decode()))
        db.commit()
        assert db.get(ModelConfig,"xml").encrypted_key!="private-test-value"
    response=client.get("/admin/models")
    assert "private-test-value" not in response.text
