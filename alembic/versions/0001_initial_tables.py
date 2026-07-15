"""initial_tables

Revision ID: 0001
Revises:
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # businesses table
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("ig_business_account_id", sa.String(255), nullable=True),
        sa.Column("ig_access_token", sa.Text(), nullable=True),
        sa.Column("ig_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("license_key", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_telegram_id"),
        sa.UniqueConstraint("license_key"),
    )

    # tracked_posts table
    op.create_table(
        "tracked_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("ig_media_id", sa.String(255), nullable=False),
        sa.Column("post_url", sa.Text(), nullable=True),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "ig_media_id", name="uq_biz_media"),
    )

    # post_responses table
    op.create_table(
        "post_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracked_post_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("content_value", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tracked_post_id"], ["tracked_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # reply_log table
    op.create_table(
        "reply_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracked_post_id", sa.Integer(), nullable=False),
        sa.Column("ig_commenter_id", sa.String(255), nullable=False),
        sa.Column("subscribe_prompt_sent_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("final_reply_sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tracked_post_id"], ["tracked_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracked_post_id", "ig_commenter_id", name="uq_post_commenter"),
    )

    # error_log table
    op.create_table(
        "error_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("error_log")
    op.drop_table("reply_log")
    op.drop_table("post_responses")
    op.drop_table("tracked_posts")
    op.drop_table("businesses")
