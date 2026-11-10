import asyncio
import socket
import pytest
import httpx
from app.services.github import GitHub
from app.services.github_public import parse_repository_url, GitHubEvidenceError
from app.services.llm import validate_endpoint, ModelFailure
@pytest.mark.parametrize("url",["http://github.com/a/b","https://github.com.evil.test/a/b","https://user@github.com/a/b","https://github.com/a/b/issues","https://127.0.0.1/a/b"])
def test_repository_urls_reject_unsafe(url):
    with pytest.raises(GitHubEvidenceError): parse_repository_url(url)
def test_repository_url():
    assert parse_repository_url("https://github.com/owner/repo.git")==("owner","repo")
def test_endpoint_rejects_unsafe_destinations():
    for url in ("http://api.openai.com/v1","https://localhost/v1","https://127.0.0.1/v1","https://evil.example/v1","https://api.openai.com@evil.example/v1"):
        with pytest.raises(ModelFailure): asyncio.run(validate_endpoint(url))
def test_first_parent_diff_and_source_commit():
    requests=[]
    def handler(request):
        requests.append(str(request.url))
        if "/commits/" in request.url.path:
            return httpx.Response(200,json={"sha":"a"*40,"parents":[{"sha":"b"*40},{"sha":"c"*40}]})
        return httpx.Response(200,json={"files":[{"filename":"T.java","status":"modified","patch":"+ change"}]})
    async def run():
        gh=GitHub()
        await gh.client.aclose()
        gh.client=httpx.AsyncClient(base_url="https://api.github.com",transport=httpx.MockTransport(handler))
        try:return await gh.diff("owner/repo","abcdef1")
        finally:await gh.close()
    data=asyncio.run(run())
    assert data["parent"]=="b"*40
    assert requests[-1].endswith("/compare/"+"b"*40+"..."+"a"*40)
def test_root_commit_has_clear_error():
    async def run():
        gh=GitHub();await gh.client.aclose()
        gh.client=httpx.AsyncClient(base_url="https://api.github.com",transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"sha":"a"*40,"parents":[]})))
        try:
            with pytest.raises(GitHubEvidenceError,match="no parent"):await gh.diff("owner/repo","abcdef1")
        finally:await gh.close()
    asyncio.run(run())
