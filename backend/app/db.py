import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, ForeignKey, JSON, Float, CheckConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .settings import DATABASE_URL
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    login: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(Text)
class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    repository: Mapped[str] = mapped_column(String)
    installation_id: Mapped[str] = mapped_column(String)
    github_repository_id: Mapped[str | None] = mapped_column(String, nullable=True)
class ModelConfig(Base):
    __tablename__ = "model_configs"
    role: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    encrypted_key: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    repository: Mapped[str] = mapped_column(String)
    commit: Mapped[str] = mapped_column(String)
    admin_test: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    artifact_key: Mapped[str] = mapped_column(String)
    diff: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_repository_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class TestEvidence(Base):
    __tablename__ = "test_evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    xml: Mapped[dict] = mapped_column(JSON)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    selected: Mapped[bool] = mapped_column(default=False)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (CheckConstraint("probability IS NULL OR (probability >= 0 AND probability <= 100)"),)

class ComponentOutput(Base):
    __tablename__ = "component_outputs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[str | None] = mapped_column(ForeignKey("test_evidence.id", ondelete="CASCADE"), nullable=True)
    component: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String, default="1")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class EvidencePayload(Base):
    __tablename__ = "evidence_payloads"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_evidence.id", ondelete="CASCADE"), index=True)
    schema_version: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String)
    prompt_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("test_id", "version", name="uq_payload_test_version"),)
class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    payload_id: Mapped[str] = mapped_column(ForeignKey("evidence_payloads.id", ondelete="CASCADE"))
    flaky_probability: Mapped[float] = mapped_column(Float)
    prompt_sha256: Mapped[str] = mapped_column(String)
    model_reference: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (CheckConstraint("flaky_probability >= 0 AND flaky_probability <= 1", name="ck_prediction_probability"),)
