import base64
import json
import re
from urllib.parse import quote
import httpx
from .github_public import GitHubEvidenceError
from .java_methods import method_name, extract_method_code, mask_java

class GitHubRequestError(GitHubEvidenceError):
    def __init__(self, message, code="GITHUB_ERROR", retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after

class GitHub:
    def __init__(self, token=None):
        self.cache = {}
        self.client = httpx.AsyncClient(base_url="https://api.github.com", timeout=30, follow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CI-Sense",
                     **({"Authorization": "Bearer " + token} if token else {})})
    async def close(self):
        await self.client.aclose()
    async def get(self, path):
        if path in self.cache:
            return self.cache[path]
        try:
            async with self.client.stream("GET", path) as response:
                if response.status_code == 429 or (response.status_code == 403 and
                    (response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after"))):
                    raise GitHubRequestError("GitHub rate limit reached. No automatic retry was attempted.",
                        "GITHUB_RATE_LIMIT", response.headers.get("retry-after") or response.headers.get("x-ratelimit-reset"))
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 12_000_000:
                        raise GitHubRequestError("GitHub response exceeds the evidence size limit.", "EVIDENCE_TOO_LARGE")
                data = json.loads(body)
                self.cache[path] = data
                return data
        except httpx.HTTPStatusError as exc:
            raise GitHubRequestError(f"GitHub returned HTTP {exc.response.status_code}; check repository access and commit.",
                                     "GITHUB_ACCESS_ERROR") from None
        except httpx.RequestError:
            raise GitHubRequestError("GitHub request failed or timed out.", "GITHUB_UNAVAILABLE") from None
    async def repositories(self):
        repositories = []
        for page in range(1, 21):
            data = await self.get(f"/user/installations?per_page=100&page={page}")
            for installation in data["installations"]:
                iid = installation["id"]
                for rp in range(1, 101):
                    result = await self.get(f"/user/installations/{iid}/repositories?per_page=100&page={rp}")
                    repositories.extend({"repository": r["full_name"], "repository_id": str(r["id"]),
                        "installation_id": str(iid), "private": r["private"]} for r in result["repositories"])
                    if len(result["repositories"]) < 100:
                        break
                else:
                    raise GitHubRequestError("Too many repositories to enumerate safely.")
            if len(data["installations"]) < 100:
                return repositories
        raise GitHubRequestError("Too many installations to enumerate.")
    async def authorize(self, repository, repository_id=None):
        return await self.get("/repositories/" + repository_id if repository_id else "/repos/" + repository)
    async def resolve_commit(self, repository, sha):
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
            raise GitHubRequestError("Enter a commit SHA with 7-40 hexadecimal characters.", "INVALID_COMMIT")
        commit = await self.get(f"/repos/{repository}/commits/{sha}")
        if not commit.get("parents"):
            raise GitHubRequestError("This commit has no parent. Select a commit with a first parent.", "ROOT_COMMIT")
        return {"commit": commit["sha"], "parent": commit["parents"][0]["sha"]}
    async def diff(self, repository, sha):
        resolved = await self.resolve_commit(repository, sha)
        data = await self.get(f"/repos/{repository}/compare/{resolved['parent']}...{resolved['commit']}")
        files = data.get("files", [])
        incomplete = len(files) >= 300 or any("patch" not in f for f in files)
        return {"status": "needs_review" if incomplete else "complete", **resolved,
            "baseline_assumption": "Tests are assumed to pass on the first parent; this has not been verified.",
            "files": [{"path": f["filename"], "previous_path": f.get("previous_filename"), "status": f["status"],
                       "patch": f.get("patch"), "patch_available": "patch" in f} for f in files],
            "message": "GitHub omitted patches or reached its 300-file comparison limit. Complete evidence cannot be guaranteed." if incomplete else None,
            "limitations": "Unavailable patches remain explicitly marked. Incomplete changes cannot produce a ready B2_o1 payload."}
    async def tree(self, repository, sha):
        data = await self.get(f"/repos/{repository}/git/trees/{sha}?recursive=1")
        if data.get("truncated"):
            raise GitHubRequestError("Repository tree is truncated; source uniqueness cannot be established.", "TREE_TRUNCATED")
        return [x["path"] for x in data["tree"] if x["type"] == "blob"]
    async def source(self, repository, sha, evidence, paths):
        classname = evidence.get("test_class", "")
        method = method_name(evidence.get("test_name", ""))
        if not classname or not method:
            return {"status": "needs_review", "message": "XML classname and name are required."}
        # Nested class ownership needs a proper nested-class resolver. Never guess a sibling method.
        if "$" in classname:
            return {"status": "needs_review", "message": "Nested-class testcase identity requires manual source resolution.", "method": method}
        async def find(classname, seen):
            if classname in seen or len(seen) >= 8:
                return [], [{"message": "Inheritance chain is cyclic or exceeds eight classes."}]
            seen = seen | {classname}
            suffix = classname.replace(".", "/") + ".java"
            candidates = [p for p in paths if p == suffix or p.endswith("/" + suffix)]
            if not candidates:
                candidates = [p for p in paths if p.rsplit("/", 1)[-1] == classname.split(".")[-1] + ".java"]
            results, supporting = [], []
            for path in candidates:
                data = await self.get(f"/repos/{repository}/contents/{quote(path, safe='/')}?ref={sha}")
                if data.get("encoding") != "base64" or data.get("size", 0) > 500_000:
                    supporting.append({"path": path, "message": "Source unavailable or larger than 500 KB."})
                    continue
                source = base64.b64decode(data["content"]).decode("utf-8")
                masked = mask_java(source)
                package = re.search(r"\bpackage\s+([\w.]+)\s*;", masked)
                if (package[1] if package else "") != classname.rpartition(".")[0]:
                    continue
                supporting.append({"path": path, "code": source, "scope": "full file"})
                code = extract_method_code(source, method)
                if code:
                    start = source[:source.find(code)].count("\n") + 1
                    results.append({"status": "complete", "path": path, "method": method, "code": code,
                        "start_line": start, "end_line": start + code.count("\n"),
                        "scope": "method", "commit": sha, "declaring_class": classname})
                    continue
                # A present but ambiguous declaration must not fall through to an inherited method.
                if re.search(r"\b" + re.escape(method) + r"\s*\(", masked):
                    continue
                parent = re.search(r"\bclass\s+" + re.escape(classname.split(".")[-1]) +
                    r"(?:\s*<[^{}]+?>)?\s+extends\s+([\w.$]+)", masked)
                if parent:
                    parent_name = parent[1]
                    if "." not in parent_name:
                        imported = re.search(r"\bimport\s+([\w.]+\." + re.escape(parent_name) + r")\s*;", masked)
                        package_name = classname.rpartition(".")[0]
                        parent_name = imported[1] if imported else (package_name + "." if package_name else "") + parent_name
                    matches, extra = await find(parent_name, seen)
                    results.extend(matches)
                    supporting.extend(extra)
            return results, supporting
        matches, supporting = await find(classname, set())
        if len(matches) == 1:
            return matches[0]
        return {"status": "ambiguous" if supporting or len(matches) > 1 else "missing", "method": method,
                "message": "No unique Java test method was resolved. Supporting files are not substituted into model input.",
                "candidates": [r.get("path") for r in supporting if r.get("path")],
                "supporting_files": supporting, "commit": sha}
