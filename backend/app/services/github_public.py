"""Read public GitHub commit evidence without accepting arbitrary API hosts."""
import re
from urllib.parse import quote, urlparse
import httpx

class GitHubEvidenceError(Exception):
    pass

def parse_repository_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
        raise GitHubEvidenceError("Enter a public GitHub repository URL (https://github.com/owner/repo).")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise GitHubEvidenceError("Enter a repository URL containing an owner and repository name.")
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo) or repo in (".", ".."):
        raise GitHubEvidenceError("Invalid GitHub repository name.")
    return owner, repo

async def get_commit_evidence(client: httpx.AsyncClient, repository_url: str, sha: str) -> dict:
    owner, repo = parse_repository_url(repository_url)
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha.strip()):
        raise GitHubEvidenceError("Enter a valid commit SHA (7–40 hexadecimal characters).")
    base = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
    try:
        response = await client.get(f"{base}/commits/{sha.strip()}", headers={"Accept": "application/vnd.github+json"}, follow_redirects=False)
        response.raise_for_status()
        commit = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GitHubEvidenceError("Could not access this public repository and commit on GitHub.") from exc
    parents = commit.get("parents") or []
    if not parents:
        raise GitHubEvidenceError("The selected commit has no parent, so a first-parent diff is unavailable.")
    selected = commit.get("sha")
    parent = parents[0].get("sha")
    if not selected or not parent:
        raise GitHubEvidenceError("GitHub returned incomplete commit information.")
    try:
        response = await client.get(f"{base}/compare/{parent}...{selected}", headers={"Accept": "application/vnd.github+json"}, follow_redirects=False)
        response.raise_for_status()
        comparison = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GitHubEvidenceError("Could not retrieve the first-parent changes from GitHub.") from exc
    return {"repository": f"{owner}/{repo}", "commit": selected, "parent": parent,
            "files": [{"path": f.get("filename"), "status": f.get("status"), "patch": f.get("patch"), "previous_path": f.get("previous_filename")} for f in comparison.get("files", [])],
            "limitations": "GitHub may omit patches for binary or large files and may limit returned changed files."}
