"""booking: Vor Ort (members say they'll be in a room on a day)

Revision ID: 8e3b6d1a4f27
Revises: 5c2a7e9d1b63
Create Date: 2026-11-10 07:00:00

"""

import sqlalchemy as sa
from alembic import op

from hubra.core.plugins.ops import has_table

revision = "8e3b6d1a4f27"
down_revision = "5c2a7e9d1b63"
branch_labels = None
depends_on = None


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _refs():
    return (
        sa.ForeignKeyConstraint(
            ["resource_id"], ["booking_resources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
    )


def upgrade():
    if not has_table("booking_onsite"):
        op.create_table(
            "booking_onsite",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("resource_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("starts", sa.Time(), nullable=True),
            sa.Column("ends", sa.Time(), nullable=True),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("key_holder", sa.Boolean(), nullable=False),
            sa.Column("comment", sa.String(300), nullable=True),
            _ts("reminded_at"),
            _ts("created_at", nullable=False),
            _ts("updated_at", nullable=False),
            *_refs(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "resource_id", "member_id", "day", name="uq_booking_onsite"
            ),
        )
        op.create_index("ix_booking_onsite_day", "booking_onsite", ["day"])
    if not has_table("booking_onsite_watches"):
        op.create_table(
            "booking_onsite_watches",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("resource_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=False),
            _ts("created_at", nullable=False),
            *_refs(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "resource_id", "member_id", name="uq_booking_onsite_watch"
            ),
        )
    if not has_table("booking_onsite_days"):
        op.create_table(
            "booking_onsite_days",
            sa.Column("day", sa.Date(), nullable=False),
            _ts("announced_at", nullable=False),
            sa.PrimaryKeyConstraint("day"),
        )


def downgrade():
    for table in ("booking_onsite_days", "booking_onsite_watches", "booking_onsite"):
        if has_table(table):
            op.drop_table(table)
