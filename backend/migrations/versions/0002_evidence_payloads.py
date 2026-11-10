"""Persist independently inspectable components and immutable B2_o1 payloads."""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("projects", sa.Column("github_repository_id", sa.String(), nullable=True))
    op.add_column("analyses", sa.Column("github_repository_id", sa.String(), nullable=True))
    op.add_column("analyses", sa.Column("parent_commit", sa.String(), nullable=True))
    op.add_column("analyses", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("model_configs", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("component_outputs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_id", sa.String(), sa.ForeignKey("test_evidence.id", ondelete="CASCADE"), nullable=True),
        sa.Column("component", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_component_outputs_analysis_id", "component_outputs", ["analysis_id"])
    op.create_table("evidence_payloads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("test_id", sa.String(), sa.ForeignKey("test_evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("prompt_reference", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("test_id", "version", name="uq_payload_test_version"))
    op.create_index("ix_evidence_payloads_test_id", "evidence_payloads", ["test_id"])
    op.create_table("predictions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("payload_id", sa.String(), sa.ForeignKey("evidence_payloads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flaky_probability", sa.Float(), nullable=False),
        sa.Column("prompt_sha256", sa.String(), nullable=False),
        sa.Column("model_reference", sa.JSON(), nullable=False),
        sa.CheckConstraint("flaky_probability >= 0 AND flaky_probability <= 1", name="ck_prediction_probability"))
    # Old nullable probability columns remain for migration compatibility; new predictions
    # exclusively use the 0..1 contract. No prediction rows are created in Stage 2.

def downgrade():
    for table in ("predictions", "evidence_payloads", "component_outputs"):
        op.drop_table(table)
    op.drop_column("model_configs", "version")
    for column in ("started_at", "parent_commit", "github_repository_id"):
        op.drop_column("analyses", column)
    op.drop_column("projects", "github_repository_id")
