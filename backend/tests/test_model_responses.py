import asyncio
import httpx
import pytest
from types import SimpleNamespace
from app.services import llm
from app.settings import cipher
def test_invalid_model_json_and_provider_errors_are_sanitized(monkeypatch):
    real_client = httpx.AsyncClient
    async def allow(url): return url
    monkeypatch.setattr(llm,"validate_endpoint",allow)
    config=SimpleNamespace(base_url="https://api.openai.com/v1",provider="openai",model="test",encrypted_key=cipher().encrypt(b"secret-key").decode())
    for status,payload in [(401,{"error":"secret-key"}),(200,{"choices":[{"message":{"content":"not JSON"}}]})]:
        transport=httpx.MockTransport(lambda req:httpx.Response(status,json=payload))
        monkeypatch.setattr(llm.httpx,"AsyncClient",lambda **kwargs:real_client(transport=transport,**kwargs))
        with pytest.raises(llm.ModelFailure) as error:
            asyncio.run(llm.invoke(config,"diff",{"test_name":"x"}))
        assert "secret-key" not in str(error.value)
def test_anthropic_adapter(monkeypatch):
    real_client=httpx.AsyncClient
    async def allow(url):return url
    monkeypatch.setattr(llm,"validate_endpoint",allow)
    def handler(req):
        assert req.url.path=="/v1/messages" and req.headers["x-api-key"]=="secret-key"
        return httpx.Response(200,json={"content":[{"type":"text","text":'{"project_change_description":"Changes a condition."}'}]})
    monkeypatch.setattr(llm.httpx,"AsyncClient",lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    config=SimpleNamespace(base_url="https://api.anthropic.com/v1",provider="anthropic",model="test",encrypted_key=cipher().encrypt(b"secret-key").decode())
    assert asyncio.run(llm.invoke(config,"diff",{}))=={"project_change_description":"Changes a condition."}
