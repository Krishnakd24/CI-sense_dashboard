"""Independent Stage 2 extraction with persisted research-compatible payloads."""
import asyncio
from sqlalchemy import select
from .db import Session, Analysis, TestEvidence, ModelConfig, User, ComponentOutput, EvidencePayload
from .settings import cipher
from .services.github import GitHub
from .services.github_public import GitHubEvidenceError
from .services.llm import invoke, ModelFailure
from .services.evidence import assemble, failure_reports, payload_hash, SCHEMA_VERSION
from .services.research_contract import prompt_reference
from .services.diff_prompt import DIFF_PROMPT_VERSION
slots = asyncio.Semaphore(2)

def save_component(db, analysis_id, test_id, component, output):
    row = db.scalar(select(ComponentOutput).where(
        ComponentOutput.analysis_id == analysis_id, ComponentOutput.test_id == test_id,
        ComponentOutput.component == component))
    if row is None:
        row = ComponentOutput(analysis_id=analysis_id, test_id=test_id, component=component,
                              schema_version="1", status="pending", output={})
        db.add(row)
    row.status = output.get("status", "complete")
    row.output = output
    db.commit()

def failure(exc):
    if isinstance(exc, (ModelFailure, GitHubEvidenceError)):
        return {"status": "failed", "code": getattr(exc, "code", "EXTRACTION_FAILED"),
                "message": str(exc), "retry_after": getattr(exc, "retry_after", None)}
    return {"status": "failed", "code": "INTERNAL_ERROR",
            "message": "Internal extraction error (" + type(exc).__name__ + ")."}

async def extract(analysis_id):
    async with slots:
        with Session() as db:
            analysis = db.get(Analysis, analysis_id)
            if not analysis or analysis.status != "running":
                return
            tests = list(db.scalars(select(TestEvidence).where(
                TestEvidence.analysis_id == analysis_id, TestEvidence.selected.is_(True))))
            gh = None
            try:
                user = db.get(User, analysis.owner_id)
                gh = GitHub(None if analysis.admin_test else cipher().decrypt(user.token.encode()).decode())
                info = await gh.authorize(analysis.repository, analysis.github_repository_id)
                if analysis.admin_test and info["private"]:
                    raise GitHubEvidenceError("Admin testing accepts public repositories only.")
                if analysis.github_repository_id and str(info["id"]) != analysis.github_repository_id:
                    raise GitHubEvidenceError("The repository identity changed. Reconnect this repository.")
                analysis.github_repository_id = str(info["id"])
                analysis.repository = info.get("full_name", analysis.repository)
                resolved = await gh.resolve_commit(analysis.repository, analysis.commit)
                analysis.commit = resolved["commit"]
                analysis.parent_commit = resolved["parent"]
                db.commit()

                analysis.diff = {"status": "running", **resolved}
                save_component(db, analysis.id, None, "git_diff", analysis.diff)
                try:
                    analysis.diff = await gh.diff(analysis.repository, analysis.commit)
                except Exception as exc:
                    analysis.diff = {**analysis.diff, **failure(exc)}
                save_component(db, analysis.id, None, "git_diff", analysis.diff)

                # Source retrieval is independent of summarization and survives diff failures.
                paths = None
                tree_error = None
                try:
                    paths = await gh.tree(analysis.repository, analysis.commit)
                except Exception as exc:
                    tree_error = failure(exc)
                for test in tests:
                    test.source = {"status": "running"}
                    save_component(db, analysis.id, test.id, "test_source", test.source)
                    try:
                        if tree_error:
                            test.source = tree_error
                        else:
                            test.source = await gh.source(analysis.repository, analysis.commit, test.xml, paths)
                    except Exception as exc:
                        test.source = failure(exc)
                    save_component(db, analysis.id, test.id, "test_source", test.source)

                if analysis.diff.get("status") == "complete":
                    raw_diff = dict(analysis.diff)
                    config = db.get(ModelConfig, "diff")
                    analysis.diff = {**raw_diff, "status": "running"}
                    save_component(db, analysis.id, None, "git_diff", analysis.diff)
                    try:
                        # Only changed-file facts enter the summarizer: no parent pass assumption.
                        summary = await invoke(config, "diff", {"files": raw_diff["files"]})
                        analysis.diff = {**raw_diff, "summary": summary, "summary_reference": {
                            "provider": config.provider, "model": config.model,
                            "configuration_version": config.version, "prompt_version": DIFF_PROMPT_VERSION}}
                    except Exception as exc:
                        analysis.diff = {**raw_diff, **failure(exc)}
                    save_component(db, analysis.id, None, "git_diff", analysis.diff)

                ready = 0
                for test in tests:
                    payload, issues = assemble(test.xml, test.source, analysis.diff)
                    if payload is not None:
                        row = EvidencePayload(test_id=test.id, schema_version=SCHEMA_VERSION, version=1,
                            payload=payload, sha256=payload_hash(payload), prompt_reference=prompt_reference())
                        db.add(row)
                        ready += 1
                    save_component(db, analysis.id, test.id, "payload", {
                        "status": "complete" if payload else "needs_review", "issues": issues,
                        "schema_version": SCHEMA_VERSION})
                if ready == len(tests):
                    analysis.status = "complete"
                elif ready:
                    analysis.status = "partial"
                elif analysis.diff.get("status") == "complete" and any(t.source.get("status") in ("missing", "ambiguous", "needs_review") for t in tests):
                    analysis.status = "needs_review"
                elif any(t.source.get("status") == "complete" for t in tests):
                    analysis.status = "partial"
                else:
                    analysis.status = "failed"
                errors = [analysis.diff.get("message")] + [t.source.get("message") for t in tests if t.source.get("status") == "failed"]
                analysis.error = "; ".join(str(e) for e in errors if e) or None
                db.commit()
            except Exception as exc:
                error = failure(exc)
                analysis.status = "failed"
                analysis.error = error["message"]
                if analysis.diff.get("status") != "complete":
                    analysis.diff = {**analysis.diff, **error}
                    save_component(db, analysis.id, None, "git_diff", analysis.diff)
                for test in tests:
                    if test.source.get("status") in (None, "running"):
                        test.source = {"status": "skipped", "message": "Repository or commit could not be resolved."}
                        save_component(db, analysis.id, test.id, "test_source", test.source)
                db.commit()
            finally:
                if gh is not None:
                    await gh.close()
