"""Explicit, single-attempt prediction from immutable saved evidence."""
import hashlib
from datetime import timedelta
from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from .db import Session, Analysis, TestEvidence, EvidencePayload, Prediction, ComponentOutput, ModelConfig, now
from .pipeline import slots
from .services.llm import invoke, ModelFailure
from .services.research_contract import render_prediction_prompt, PREDICTION_PROMPT_VERSION, validate_prediction_response
FRIENDLY = "Analysis could not be completed. Please contact the administrator."

async def predict(payload_id, component_id, prompt, template_hash):
    async with slots:
        with Session() as db:
            state = db.get(ComponentOutput, component_id)
            payload = db.get(EvidencePayload, payload_id)
            if not state or not payload or state.status != "running":
                return
            try:
                config = db.get(ModelConfig, "classifier")
                if config is None:
                    raise ModelFailure("The central model configuration is missing.")
                reference = {"provider": config.provider, "model": config.model,
                             "configuration_version": config.version,
                             "rendered_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                             "message_role": "user", "payload_sha256": payload.sha256,
                             "prompt_version": PREDICTION_PROMPT_VERSION,
                             "research_prompt_sha256": payload.prompt_reference.get("sha256")}
                result = validate_prediction_response(await invoke(config, "prediction", prompt))
                db.add(Prediction(payload_id=payload.id, flaky_probability=result["flaky_probability"],
                                 prompt_sha256=template_hash, model_reference=reference))
                state.status = "complete"
                state.output = {"status": "complete", "model_reference": reference, "reasons": result["reasons"]}
                db.commit()
            except Exception as exc:
                db.rollback()
                state = db.get(ComponentOutput, component_id)
                if state:
                    state.status = "failed"
                    state.output = {"status": "failed", "message": FRIENDLY,
                        "technical_error": str(exc) if isinstance(exc, ModelFailure) else "Prediction failed (" + type(exc).__name__ + ")."}
                    db.commit()

def register_prediction_routes(app, database, current_user, owned):
    @app.post("/analyses/{aid}/tests/{tid}/predict", status_code=202)
    def start_prediction(aid: str, tid: str, tasks: BackgroundTasks,
                         user=Depends(current_user), db=Depends(database)):
        owned(db, user, aid)
        # Serialize requests and deletion on this analysis using the same database row lock.
        analysis = db.scalar(select(Analysis).where(Analysis.id == aid).with_for_update().execution_options(populate_existing=True))
        if not analysis or analysis.status in ("draft", "running", "deleting"):
            raise HTTPException(409, "Wait for evidence extraction to finish.")
        test = db.get(TestEvidence, tid)
        if not test or test.analysis_id != aid or not test.selected:
            raise HTTPException(404, "Selected test not found.")
        payload = db.scalar(select(EvidencePayload).where(EvidencePayload.test_id == tid).order_by(EvidencePayload.version.desc()))
        if not payload:
            raise HTTPException(409, "This test does not have a complete B2_o1 evidence payload.")
        state = db.scalar(select(ComponentOutput).where(ComponentOutput.test_id == tid, ComponentOutput.component == "prediction"))
        if state:
            raise HTTPException(409, "Prediction has already been requested for this test. Inspect its saved result.")
        if not db.get(ModelConfig, "classifier"):
            raise HTTPException(409, "Ask the administrator to configure the central model first.")
        active = db.scalar(select(func.count()).select_from(ComponentOutput).where(
            ComponentOutput.component == "prediction", ComponentOutput.status == "running"))
        extraction_count = db.scalar(select(func.count()).select_from(Analysis).where(Analysis.status == "running"))
        if active + extraction_count >= 4:
            raise HTTPException(429, "The server is processing other analyses. Try again shortly.")
        used = db.scalar(select(func.count()).select_from(ComponentOutput).join(Analysis).where(
            Analysis.owner_id == user.id, ComponentOutput.component == "prediction",
            ComponentOutput.created_at > now() - timedelta(hours=1)))
        if used >= 20:
            raise HTTPException(429, "Hourly prediction limit reached.")
        try:
            prompt, template_hash = render_prediction_prompt(payload.payload, payload.prompt_reference.get("sha256"))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        state = ComponentOutput(analysis_id=aid, test_id=tid, component="prediction",
                                status="running", schema_version=PREDICTION_PROMPT_VERSION,
                                output={"status": "running"})
        db.add(state); db.commit()
        tasks.add_task(predict, payload.id, state.id, prompt, template_hash)
        return {"status": "running"}
