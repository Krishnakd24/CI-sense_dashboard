import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect
from app.db import Session, EvidencePayload, ComponentOutput, TestEvidence
from app.services.evidence import payload_hash
from test_api import upload

def test_payload_route_ownership_and_cleanup(client):
    aid=upload(client)
    tid=client.get("/analyses/"+aid).json()["tests"][0]["id"]
    assert client.get("/analyses/"+aid+"/tests/"+tid+"/payload").status_code==409
    payload={"test_code":"void x() {}","failure_reports":[{"execution_result":"FAIL"}],
             "project_change_description":"Changes a condition."}
    with Session() as db:
        db.add(EvidencePayload(test_id=tid,version=1,schema_version="b2_o1-v1",payload=payload,
                               sha256=payload_hash(payload),prompt_reference={}))
        db.commit()
    assert client.get("/analyses/"+aid+"/tests/"+tid+"/payload").json()==payload
    assert client.get("/analyses/"+aid+"/report").content.startswith(b"<testsuite>")
    assert client.delete("/analyses/"+aid).status_code==200
    with Session() as db:
        assert db.query(EvidencePayload).count()==0
        assert db.query(ComponentOutput).count()==0

def test_migration_creates_stage2_tables(tmp_path):
    database=tmp_path/"migration.sqlite"
    environment={**os.environ,"DATABASE_URL":"sqlite+pysqlite:///"+database.as_posix()}
    result=subprocess.run([sys.executable,"-m","alembic","upgrade","head"],
                          cwd=Path(__file__).resolve().parents[1],env=environment,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    engine=create_engine(environment["DATABASE_URL"])
    try:
        inspector=inspect(engine)
        assert {"component_outputs","evidence_payloads","predictions"}<=set(inspector.get_table_names())
        assert "parent_commit" in {c["name"] for c in inspector.get_columns("analyses")}
    finally:engine.dispose()
