import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from .body_limit import BodyLimit
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from .db import Session, User, LoginSession, Project, Analysis, TestEvidence, ModelConfig, ComponentOutput, EvidencePayload, Prediction, uid, now
from .settings import FRONTEND_URL, PUBLIC_API_URL, COOKIE_SECURE, ADMIN_IDS, cipher
from . import storage
from .pipeline import extract, save_component
from .evidence_api import test_view, register_evidence_routes
from .prediction import register_prediction_routes
from .services.evidence import group_failures, failure_reports
from .services.xml_parser import parse_report, MAX_XML
from .services.github import GitHub
from .services.github_public import parse_repository_url, GitHubEvidenceError
from .services.llm import validate_endpoint, invoke, ModelFailure

FRIENDLY = "Analysis could not be completed. Please contact the administrator."
@asynccontextmanager
async def lifespan(app):
    # Single backend process: interrupted executions are never retried automatically.
    with Session() as db:
        for a in db.scalars(select(Analysis).where(Analysis.status == "running")):
            a.status = "failed"; a.error = "Backend stopped during evidence extraction."
            if a.diff.get("status") == "running": a.diff = {**a.diff, "status": "failed"}
            for t in db.scalars(select(TestEvidence).where(TestEvidence.analysis_id == a.id)):
                if t.validation.get("status") == "running": t.validation = {"status": "failed"}
                if t.source.get("status") == "running": t.source = {"status": "failed"}
        for component in db.scalars(select(ComponentOutput).where(ComponentOutput.status == "running")):
            component.status = "failed"
            component.output = {**component.output, "status": "failed", "message": "Backend stopped during execution."}
        db.commit()
    yield

app = FastAPI(title="CI-Sense · Evidence API", lifespan=lifespan)
app.add_middleware(BodyLimit)
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_URL], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])
@app.middleware("http")
async def csrf(request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.headers.get("origin") != FRONTEND_URL:
        return JSONResponse({"detail": "Invalid request origin."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({"detail": "Invalid request fields. Check the form values."}, status_code=422)
@app.exception_handler(GitHubEvidenceError)
async def github_error(request, exc):
    code = getattr(exc, "code", "GITHUB_ERROR")
    return JSONResponse({"detail": str(exc), "code": code, "retry_after": getattr(exc, "retry_after", None)}, status_code=429 if code == "GITHUB_RATE_LIMIT" else 400)
@app.exception_handler(ModelFailure)
async def model_error(request, exc): return JSONResponse({"detail": str(exc)}, status_code=400)
def database():
    with Session() as db: yield db
def current_user(request: Request, db=Depends(database)):
    raw = request.cookies.get("ci_session", "")
    session = db.get(LoginSession, hashlib.sha256(raw.encode()).hexdigest())
    if not session or session.expires.replace(tzinfo=timezone.utc) < now():
        raise HTTPException(401, "Sign in with GitHub.")
    user = db.get(User, session.user_id)
    if not user: raise HTTPException(401, "Sign in with GitHub.")
    return user
def admin(user=Depends(current_user)):
    if user.id not in ADMIN_IDS: raise HTTPException(403, "Administrator access required.")
    return user
limits = defaultdict(deque)
def limit(user, action, maximum):
    bucket = limits[(user.id, action)]
    stamp = time.monotonic()
    while bucket and bucket[0] < stamp - 3600: bucket.popleft()
    if len(bucket) >= maximum: raise HTTPException(429, "Hourly request limit reached. Please try again later.")
    bucket.append(stamp)
def owned(db, user, aid):
    a = db.get(Analysis, aid)
    if not a or a.owner_id != user.id or (a.admin_test and user.id not in ADMIN_IDS): raise HTTPException(404, "Analysis not found.")
    return a
def project_owned(db, user, pid):
    p = db.get(Project, pid)
    if not p or p.owner_id != user.id: raise HTTPException(404, "Project not found.")
    return p
def github_user(user): return GitHub(cipher().decrypt(user.token.encode()).decode())
def serialize(a, user):
    return {"id": a.id, "repository": a.repository, "commit": a.commit, "project_id": a.project_id,
        "admin_test": a.admin_test, "status": a.status, "created_at": a.created_at,
        "message": FRIENDLY if a.status in ("failed", "partial") else None, "parent_commit": a.parent_commit,
        "technical_error": a.error if user.id in ADMIN_IDS else None}
@app.get("/health")
def health(): return {"status": "ok", "layer": 2, "stage": 2}
@app.get("/auth/login")
def login():
    client = os.getenv("GITHUB_CLIENT_ID")
    if not client: raise HTTPException(503, "GitHub login has not been configured.")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client, "redirect_uri": PUBLIC_API_URL + "/auth/callback", "state": state}))
    response.set_cookie("ci_oauth", cipher().encrypt(state.encode()).decode(), httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=600)
    return response
@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = "", db=Depends(database)):
    try: expected = cipher().decrypt(request.cookies.get("ci_oauth", "").encode(), ttl=600).decode()
    except Exception: raise HTTPException(400, "Login expired. Please sign in again.")
    if not code or not state or not secrets.compare_digest(expected, state): raise HTTPException(400, "Invalid login state.")
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
            json={"client_id": os.environ["GITHUB_CLIENT_ID"], "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                  "code": code, "redirect_uri": PUBLIC_API_URL + "/auth/callback"})
        if response.status_code != 200: raise HTTPException(400, "GitHub login failed.")
        token = response.json().get("access_token")
        if not token: raise HTTPException(400, "GitHub authorization failed.")
    gh = GitHub(token)
    try: profile = await gh.get("/user")
    finally: await gh.close()
    user = db.get(User, str(profile["id"]))
    if not user: user = User(id=str(profile["id"]), login=profile["login"], token=""); db.add(user)
    user.login = profile["login"]; user.token = cipher().encrypt(token.encode()).decode()
    raw = secrets.token_urlsafe(48)
    db.add(LoginSession(id=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires=now() + timedelta(hours=8)))
    db.commit()
    response = RedirectResponse(FRONTEND_URL)
    response.delete_cookie("ci_oauth")
    response.set_cookie("ci_session", raw, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=28800)
    return response
@app.post("/auth/logout")
def logout(request: Request, db=Depends(database)):
    db.execute(delete(LoginSession).where(LoginSession.id == hashlib.sha256(request.cookies.get("ci_session", "").encode()).hexdigest())); db.commit()
    response = JSONResponse({"ok": True}); response.delete_cookie("ci_session"); return response
@app.get("/me")
def me(user=Depends(current_user)):
    slug = os.getenv("GITHUB_APP_SLUG", "")
    return {"login": user.login, "is_admin": user.id in ADMIN_IDS,
            "installation_url": "https://github.com/apps/" + slug + "/installations/new" if slug else None}
@app.get("/repositories")
async def repositories(user=Depends(current_user)):
    limit(user, "repositories", 30)
    gh = github_user(user)
    try: return await gh.repositories()
    finally: await gh.close()
class ProjectInput(BaseModel):
    repository: str = Field(max_length=200)
    installation_id: str = Field(pattern=r"^\d+$")
@app.post("/projects")
async def create_project(body: ProjectInput, user=Depends(current_user), db=Depends(database)):
    gh = github_user(user)
    try:
        match = next((r for r in await gh.repositories() if r["repository"] == body.repository and r["installation_id"] == body.installation_id), None)
        if match is None:
            raise HTTPException(403, "Repository is not authorized for your GitHub App installation.")
    finally: await gh.close()
    existing = db.scalar(select(Project).where(Project.owner_id == user.id, Project.repository == body.repository))
    if existing: return {"id": existing.id}
    p = Project(owner_id=user.id, github_repository_id=match.get("repository_id"), **body.model_dump()); db.add(p); db.commit(); return {"id": p.id}
@app.get("/projects")
def projects(user=Depends(current_user), db=Depends(database)):
    return [{"id": p.id, "repository": p.repository, "analysis_count": db.scalar(select(func.count()).select_from(Analysis).where(Analysis.project_id == p.id))}
            for p in db.scalars(select(Project).where(Project.owner_id == user.id))]
@app.get("/projects/{pid}")
def project_detail(pid: str, user=Depends(current_user), db=Depends(database)):
    p = project_owned(db, user, pid)
    return {"id": p.id, "repository": p.repository, "analysis_count": db.scalar(select(func.count()).select_from(Analysis).where(Analysis.project_id == pid))}
@app.get("/projects/{pid}/connection")
async def connection(pid: str, user=Depends(current_user), db=Depends(database)):
    p = project_owned(db, user, pid); gh = github_user(user)
    try:
        info = await gh.authorize(p.repository, p.github_repository_id)
        return {"connected": True, "repository": p.repository, "private": info["private"]}
    finally: await gh.close()
@app.get("/projects/{pid}/commits")
async def commits(pid: str, user=Depends(current_user), db=Depends(database)):
    p = project_owned(db, user, pid); gh = github_user(user)
    try:
        info = await gh.authorize(p.repository, p.github_repository_id)
        p.repository = info.get("full_name", p.repository); db.commit()
        rows = await gh.get("/repos/" + p.repository + "/commits?per_page=30")
        return [{"sha": r["sha"], "message": r["commit"]["message"].split("\n")[0]} for r in rows]
    finally: await gh.close()
@app.post("/analyses")
async def create_analysis(report: UploadFile = File(...), commit: str = Form(...), repository_url: str = Form(""),
                          project_id: str = Form(""), admin_test: bool = Form(False),
                          user=Depends(current_user), db=Depends(database)):
    limit(user, "upload", 30)
    import re
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit): raise HTTPException(400, "Enter a valid commit SHA.")
    if admin_test:
        if user.id not in ADMIN_IDS: raise HTTPException(403, "Administrator access required.")
        owner, repo = parse_repository_url(repository_url); repository = owner + "/" + repo
    else:
        project = project_owned(db, user, project_id)
        repository = project.repository
    data = await report.read(MAX_XML + 1)
    try: tests = group_failures(parse_report(data))
    except Exception: raise HTTPException(400, "Invalid JUnit XML, no failures, or report exceeds 5 MB / 200 failures.")
    gh = GitHub() if admin_test else github_user(user)
    try:
        info = await gh.authorize(repository, None if admin_test else project.github_repository_id)
        if admin_test and info["private"]: raise HTTPException(403, "Admin testing accepts public repositories only.")
        repository = info.get("full_name", repository)
        resolved = await gh.resolve_commit(repository, commit)
    finally: await gh.close()
    aid = uid(); key = aid + "/report.xml"
    storage.put(key, data)
    try:
        a = Analysis(id=aid, owner_id=user.id, repository=repository, commit=resolved["commit"],
            parent_commit=resolved["parent"], github_repository_id=str(info["id"]),
            project_id=None if admin_test else project_id, admin_test=admin_test, artifact_key=key)
        db.add(a); db.flush()
        for entry in tests:
            test = TestEvidence(analysis_id=aid, name=entry["test_class"] + "#" + entry["test_name"], xml=entry)
            db.add(test); db.flush()
            db.add(ComponentOutput(analysis_id=aid, test_id=test.id, component="xml_parser", status="complete",
                schema_version="b1-v1", output={"status": "complete", "failure_reports": failure_reports(entry)}))
        db.commit()
    except Exception:
        db.rollback(); storage.delete(key); raise
    return {"id": aid}
@app.get("/analyses")
def history(admin_test: bool = False, project_id: str | None = None, user=Depends(current_user), db=Depends(database)):
    if admin_test and user.id not in ADMIN_IDS: raise HTTPException(403, "Administrator access required.")
    query = select(Analysis).where(Analysis.owner_id == user.id, Analysis.admin_test == admin_test)
    if project_id: query = query.where(Analysis.project_id == project_id)
    return [serialize(a, user) for a in db.scalars(query.order_by(Analysis.created_at.desc()).limit(200))]
@app.get("/analyses/{aid}")
def detail(aid: str, user=Depends(current_user), db=Depends(database)):
    a = owned(db, user, aid)
    return {**serialize(a, user), "diff": a.diff, "tests": [
        test_view(db, t, a, user.id in ADMIN_IDS)
        for t in db.scalars(select(TestEvidence).where(TestEvidence.analysis_id == aid))]}
class Selection(BaseModel):
    test_ids: list[str] = Field(min_length=1, max_length=20)
@app.post("/analyses/{aid}/extract", status_code=202)
def start(aid: str, body: Selection, tasks: BackgroundTasks, user=Depends(current_user), db=Depends(database)):
    a = owned(db, user, aid)
    if a.status != "draft": raise HTTPException(409, "This analysis has already started.")
    limit(user, "extract", 10)
    recent = db.scalar(select(func.count()).select_from(Analysis).where(Analysis.owner_id == user.id, Analysis.status != "draft", Analysis.started_at > now() - timedelta(hours=1)))
    if recent >= 10: raise HTTPException(429, "Hourly analysis limit reached.")
    if db.scalar(select(func.count()).select_from(Analysis).where(Analysis.status == "running")) >= 4:
        raise HTTPException(429, "The server is processing other analyses. Try again shortly.")
    tests = list(db.scalars(select(TestEvidence).where(TestEvidence.analysis_id == aid)))
    if set(body.test_ids) - {t.id for t in tests}: raise HTTPException(400, "Invalid failing test selection.")
    if not db.get(ModelConfig, "diff"): raise HTTPException(409, "Ask the administrator to configure the Git diff summarizer first.")
    # Atomic state transition prevents duplicate funded executions.
    from sqlalchemy import update
    changed = db.execute(update(Analysis).where(Analysis.id == aid, Analysis.status == "draft").values(status="running", started_at=now()))
    if changed.rowcount != 1: raise HTTPException(409, "Analysis already started.")
    for t in tests: t.selected = t.id in body.test_ids
    db.commit(); tasks.add_task(extract, aid)
    return {"status": "running"}
@app.delete("/analyses/{aid}")
def remove(aid: str, user=Depends(current_user), db=Depends(database)):
    owned(db, user, aid)
    a = db.scalar(select(Analysis).where(Analysis.id == aid).with_for_update().execution_options(populate_existing=True))
    if not a: raise HTTPException(404, "Analysis not found.")
    if db.scalar(select(ComponentOutput.id).where(ComponentOutput.analysis_id == aid, ComponentOutput.component == "prediction", ComponentOutput.status == "running")):
        raise HTTPException(409, "Wait for prediction to finish before deleting.")
    if a.status == "running": raise HTTPException(409, "Wait for extraction to finish before deleting.")
    from sqlalchemy import update
    changed = db.execute(update(Analysis).where(Analysis.id == aid, Analysis.status != "running").values(status="deleting"))
    if changed.rowcount != 1: raise HTTPException(409, "Extraction started; wait before deleting.")
    # This transaction prevents extraction from starting during artifact cleanup.
    # If storage fails, rollback retains the record for another deletion attempt.
    storage.delete(a.artifact_key)
    test_ids = select(TestEvidence.id).where(TestEvidence.analysis_id == aid)
    payload_ids = select(EvidencePayload.id).where(EvidencePayload.test_id.in_(test_ids))
    db.execute(delete(Prediction).where(Prediction.payload_id.in_(payload_ids)))
    db.execute(delete(EvidencePayload).where(EvidencePayload.test_id.in_(test_ids)))
    db.execute(delete(ComponentOutput).where(ComponentOutput.analysis_id == aid))
    db.execute(delete(TestEvidence).where(TestEvidence.analysis_id == aid)); db.delete(a); db.commit()
    return {"ok": True}
@app.get("/analyses/{aid}/approved-evidence")
def approved_evidence(aid: str, user=Depends(current_user), db=Depends(database)):
    a = owned(db, user, aid)
    if a.status not in ("complete", "partial"): raise HTTPException(409, "Evidence extraction is not complete.")
    rows = db.scalars(select(EvidencePayload).join(TestEvidence).where(TestEvidence.analysis_id == aid)).all()
    return {"analysis_id": aid, "payloads": [{"test_id": row.test_id, "payload": row.payload, "sha256": row.sha256} for row in rows]}
ROLES = ("diff", "classifier")
class ConfigInput(BaseModel):
    provider: str = Field(pattern="^(openai|anthropic)$")
    base_url: str = Field(max_length=500)
    model: str = Field(min_length=1, max_length=150)
    api_key: str | None = Field(default=None, max_length=2000)
@app.get("/admin/models")
def model_configs(user=Depends(admin), db=Depends(database)):
    return [{"role": role, **({"provider": c.provider, "base_url": c.base_url, "model": c.model, "key_configured": True} if (c := db.get(ModelConfig, role)) else {"key_configured": False})} for role in ROLES]
@app.put("/admin/models/{role}")
async def save_config(role: str, body: ConfigInput, user=Depends(admin), db=Depends(database)):
    if role not in ROLES: raise HTTPException(404)
    await validate_endpoint(body.base_url)
    c = db.get(ModelConfig, role)
    if not c and not body.api_key: raise HTTPException(400, "An API key is required for the initial configuration.")
    if not c: c = ModelConfig(role=role, version=1); db.add(c)
    else: c.version += 1
    c.provider = body.provider; c.base_url = body.base_url.rstrip("/"); c.model = body.model
    if body.api_key: c.encrypted_key = cipher().encrypt(body.api_key.encode()).decode()
    db.commit(); return {"key_configured": True}
@app.post("/admin/models/{role}/test")
async def test_config(role: str, user=Depends(admin), db=Depends(database)):
    if role not in ROLES: raise HTTPException(404)
    limit(user, "connection-test", 20)
    return await invoke(db.get(ModelConfig, role), "connection")

register_evidence_routes(app, database, current_user, owned)

@app.post("/admin/analyses")
async def create_admin_analysis(report: UploadFile = File(...), commit: str = Form(...),
                                repository_url: str = Form(...), user=Depends(admin), db=Depends(database)):
    return await create_analysis(report, commit, repository_url, "", True, user, db)

register_prediction_routes(app, database, current_user, owned)
