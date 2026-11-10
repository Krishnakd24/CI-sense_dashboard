"""Backend-only, no retries, bounded requests to deployment-approved providers."""
import asyncio
import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, Field, ConfigDict
from .diff_prompt import DIFF_INSTRUCTIONS
from .research_contract import validate_prediction_response
from ..settings import cipher
class ModelFailure(Exception): pass
class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_change_description: str = Field(min_length=1, max_length=8000)
async def validate_endpoint(url):
    parsed = urlsplit(url)
    allowed = set(x.strip().lower() for x in os.getenv("LLM_ALLOWED_HOSTS", "api.openai.com,api.anthropic.com,generativelanguage.googleapis.com").split(","))
    try: port = parsed.port
    except ValueError: raise ModelFailure("Invalid endpoint port.") from None
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or port not in (None, 443) or parsed.hostname not in allowed:
        raise ModelFailure("Endpoint must use HTTPS and a hostname approved by the deployment administrator.")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError()
    except Exception:
        raise ModelFailure("Endpoint DNS must resolve exclusively to public addresses.") from None
    return url.rstrip("/")
async def invoke(config, purpose, evidence=None):
    if purpose not in ("diff", "connection", "prediction"): raise ModelFailure("Unsupported model operation.")
    if config is None: raise ModelFailure("The model configuration is missing.")
    base = await validate_endpoint(config.base_url)
    schema = Summary
    if purpose == "prediction":
        if not isinstance(evidence, str): raise ModelFailure("Prediction requires a rendered B2_o1 prompt.")
        instruction = None
        payload = evidence
    elif purpose == "connection":
        instruction = 'Return JSON only: {"ok": true}.'
        payload = "Connection check"
    else:
        instruction = DIFF_INSTRUCTIONS
        payload = json.dumps(evidence, ensure_ascii=False)
    if len(payload) > 180_000: raise ModelFailure("Evidence exceeds the configured model input limit; no truncated evidence was submitted.")
    key = cipher().decrypt(config.encrypted_key.encode()).decode()
    messages = [{"role": "user", "content": payload}]
    headers = {}
    if config.provider == "anthropic":
        url = base + "/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": config.model, "max_tokens": 3000, "messages": messages}
        if instruction is not None: body["system"] = instruction
    elif config.provider == "openai":
        url = base + "/chat/completions"
        headers = {"Authorization": "Bearer " + key}
        body = {"model": config.model, "messages": ([{"role": "system", "content": instruction}] if instruction is not None else []) + messages, "max_tokens": 3000}
    else: raise ModelFailure("Unsupported provider protocol.")
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=False, trust_env=False) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code >= 300:
                    raise ModelFailure(f"Provider returned HTTP {response.status_code}. Check endpoint, model, credentials and quota.")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000: raise ModelFailure("Provider response exceeds the size limit.")
            data = json.loads(raw)
        content = "".join(x.get("text", "") for x in data["content"] if x.get("type") == "text") if config.provider == "anthropic" else data["choices"][0]["message"]["content"]
        result = json.loads(content)
        if purpose == "connection":
            if result != {"ok": True}: raise ValueError()
            return {"ok": True}
        if purpose == "prediction": return validate_prediction_response(result)
        return schema.model_validate(result).model_dump()
    except ModelFailure: raise
    except httpx.RequestError: raise ModelFailure("Provider connection failed or timed out.") from None
    except Exception: raise ModelFailure("Provider returned an invalid structured response.") from None
