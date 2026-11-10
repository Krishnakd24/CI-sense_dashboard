"""Initial Layer 1 schema, with nullable future prediction fields."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("users", sa.Column("id",sa.String(),primary_key=True),sa.Column("login",sa.String(),nullable=False),sa.Column("token",sa.Text(),nullable=False))
    op.create_table("sessions",sa.Column("id",sa.String(),primary_key=True),sa.Column("user_id",sa.String(),sa.ForeignKey("users.id"),nullable=False),sa.Column("expires",sa.DateTime(timezone=True),nullable=False))
    op.create_table("projects",sa.Column("id",sa.String(),primary_key=True),sa.Column("owner_id",sa.String(),sa.ForeignKey("users.id"),nullable=False),sa.Column("repository",sa.String(),nullable=False),sa.Column("installation_id",sa.String(),nullable=False))
    op.create_index("ix_projects_owner_id","projects",["owner_id"])
    op.create_table("model_configs",sa.Column("role",sa.String(),primary_key=True),sa.Column("provider",sa.String(),nullable=False),sa.Column("base_url",sa.String(),nullable=False),sa.Column("model",sa.String(),nullable=False),sa.Column("encrypted_key",sa.Text(),nullable=False))
    op.create_table("analyses",sa.Column("id",sa.String(),primary_key=True),sa.Column("owner_id",sa.String(),sa.ForeignKey("users.id"),nullable=False),sa.Column("project_id",sa.String(),sa.ForeignKey("projects.id"),nullable=True),sa.Column("repository",sa.String(),nullable=False),sa.Column("commit",sa.String(),nullable=False),sa.Column("admin_test",sa.Boolean(),nullable=False),sa.Column("status",sa.String(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("artifact_key",sa.String(),nullable=False),sa.Column("diff",sa.JSON(),nullable=False),sa.Column("error",sa.Text(),nullable=True))
    op.create_index("ix_analyses_owner_id","analyses",["owner_id"])
    op.create_table("test_evidence",sa.Column("id",sa.String(),primary_key=True),sa.Column("analysis_id",sa.String(),sa.ForeignKey("analyses.id",ondelete="CASCADE"),nullable=False),sa.Column("name",sa.String(),nullable=False),sa.Column("xml",sa.JSON(),nullable=False),sa.Column("validation",sa.JSON(),nullable=False),sa.Column("source",sa.JSON(),nullable=False),sa.Column("selected",sa.Boolean(),nullable=False),sa.Column("probability",sa.Float(),nullable=True),sa.Column("explanation",sa.Text(),nullable=True),sa.CheckConstraint("probability IS NULL OR (probability >= 0 AND probability <= 100)"))
    op.create_index("ix_test_evidence_analysis_id","test_evidence",["analysis_id"])
def downgrade():
    for table in ("test_evidence","analyses","model_configs","projects","sessions","users"): op.drop_table(table)
