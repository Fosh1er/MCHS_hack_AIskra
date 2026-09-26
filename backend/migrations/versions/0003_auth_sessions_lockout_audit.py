"""П. 0.3: сессии входа (auth_sessions), защита от подбора пароля (users.failed_attempts, locked_until),
ключи поиска без учёта регистра (users.search_key, audit_log.actor_key, description_key), автор записи аудита
(audit_log.actor_login, actor_role).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 17:08:11.808711
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("arm_number", sa.String(length=16), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.add_column("audit_log", sa.Column("actor_login", sa.String(length=64), nullable=True))
    op.add_column("audit_log", sa.Column("actor_role", sa.String(length=16), nullable=True))
    op.add_column("audit_log", sa.Column("actor_key", sa.String(length=320), nullable=True))
    op.add_column("audit_log", sa.Column("description_key", sa.Text(), nullable=True))
    op.create_index(op.f("ix_audit_log_actor_login"), "audit_log", ["actor_login"], unique=False)
    op.add_column("users", sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("search_key", sa.String(length=320), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "search_key")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_attempts")
    op.drop_index(op.f("ix_audit_log_actor_login"), table_name="audit_log")
    op.drop_column("audit_log", "description_key")
    op.drop_column("audit_log", "actor_key")
    op.drop_column("audit_log", "actor_role")
    op.drop_column("audit_log", "actor_login")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
