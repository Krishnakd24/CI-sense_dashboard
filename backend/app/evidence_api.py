"""Owner-protected read contracts for persisted evidence and raw uploads."""
from fastapi import Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from .db import TestEvidence, EvidencePayload, ComponentOutput, Prediction
from .services.evidence import failure_reports
from . import storage

def test_view(db, test, analysis, is_admin=False):
    payload = db.scalar(select(EvidencePayload).where(EvidencePayload.test_id == test.id).order_by(EvidencePayload.version.desc()))
    state = db.scalar(select(ComponentOutput).where(
        ComponentOutput.test_id == test.id, ComponentOutput.component == "payload"))
    prediction_state = db.scalar(select(ComponentOutput).where(ComponentOutput.test_id == test.id, ComponentOutput.component == "prediction"))
    prediction = db.scalar(select(Prediction).where(Prediction.payload_id == payload.id)) if payload else None
    outcome = {"status": prediction_state.status if prediction_state else "not_started"}
    if prediction:
        outcome["reasons"] = prediction_state.output.get("reasons", []) if prediction_state else []
        outcome.update(status="complete", flaky_probability=prediction.flaky_probability, model_reference=prediction.model_reference, prompt_sha256=prediction.prompt_sha256)
    elif prediction_state and prediction_state.status == "failed":
        outcome["message"] = "Analysis could not be completed. Please contact the administrator."
        if is_admin: outcome["technical_error"] = prediction_state.output.get("technical_error", prediction_state.output.get("message"))
    return {
        "prediction": outcome,
        "id": test.id, "name": test.name, "selected": test.selected,
        "xml": test.xml, "xml_state": {"status": "complete", "review": "manual"},
        "failure_reports": failure_reports(test.xml), "source": test.source,
        "payload_state": state.output if state else {"status": "pending"},
        "payload": payload.payload if payload else None,
        "payload_reference": {"id": payload.id, "version": payload.version, "sha256": payload.sha256,
            "schema_version": payload.schema_version, "prompt": payload.prompt_reference} if payload else None,
    }

def register_evidence_routes(app, database, current_user, owned):
    @app.get("/analyses/{aid}/tests/{tid}/payload")
    def read_payload(aid: str, tid: str, user=Depends(current_user), db=Depends(database)):
        owned(db, user, aid)
        test = db.get(TestEvidence, tid)
        if not test or test.analysis_id != aid:
            raise HTTPException(404, "Test not found.")
        row = db.scalar(select(EvidencePayload).where(EvidencePayload.test_id == tid).order_by(EvidencePayload.version.desc()))
        if row is None:
            raise HTTPException(409, "B2_o1 evidence is not ready. Inspect component issues.")
        return row.payload

    @app.get("/analyses/{aid}/report")
    def read_report(aid: str, user=Depends(current_user), db=Depends(database)):
        analysis = owned(db, user, aid)
        return Response(storage.get(analysis.artifact_key), media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="report.xml"'})
