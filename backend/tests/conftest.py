import os
from cryptography.fernet import Fernet
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test-ci-sense.db"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["ADMIN_GITHUB_IDS"] = "1"
os.environ["COOKIE_SECURE"] = "false"
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, Session, User
from app.main import app, current_user, limits
from app.settings import cipher
@pytest.fixture
def client(tmp_path, monkeypatch):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    monkeypatch.setenv("ARTIFACT_DIR",str(tmp_path))
    monkeypatch.setenv("S3_BUCKET","")
    limits.clear()
    from app.services.github import GitHub
    async def authorize(self, *args): return {"id": 123, "full_name": "example/repo", "private": False}
    async def resolve(self, *args): return {"commit": "a"*40, "parent": "b"*40}
    monkeypatch.setattr(GitHub, "authorize", authorize)
    monkeypatch.setattr(GitHub, "resolve_commit", resolve)
    with Session() as db:
        db.add_all([User(id="1",login="admin",token=cipher().encrypt(b"test-token").decode()),User(id="2",login="other",token=cipher().encrypt(b"test-token").decode())]); db.commit()
    def as_admin():
        with Session() as db: return db.get(User,"1")
    app.dependency_overrides[current_user] = as_admin
    with TestClient(app,headers={"Origin":"http://localhost:3000"}) as c: yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
