"""booking: Vor Ort repeat, check-out, joining, calendar feed, key pings

Revision ID: 6a1c4e8b2d90
Revises: 3d9f5b7c2a10
Create Date: 2026-11-11 08:00:00

"""

import sqlalchemy as sa
from alembic import op

from hubra.core.plugins.ops import columns, has_table

revision = "6a1c4e8b2d90"
down_revision = "3d9f5b7c2a10"
branch_labels = None
depends_on = None

NEW = (
    ("series", lambda: sa.Column("series", sa.String(22), nullable=True)),
    (
        "left_at",
        lambda: sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    ),
    (
        "joinable",
        lambda: sa.Column(
            "joinable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    ),
    ("joins_id", lambda: sa.Column("joins_id", sa.Integer(), nullable=True)),
)


def upgrade():
    have = columns("booking_onsite")
    if have:
        for name, make in NEW:
            if name not in have:
                op.add_column("booking_onsite", make())
        if "joins_id" not in have:
            op.create_foreign_key(
                "fk_booking_onsite_joins",
                "booking_onsite",
                "booking_onsite",
                ["joins_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "series" not in have:
            op.create_index("ix_booking_onsite_series", "booking_onsite", ["series"])
    if not has_table("booking_onsite_feeds"):
        op.create_table(
            "booking_onsite_feeds",
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(43), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("member_id"),
            sa.UniqueConstraint("token", name="uq_booking_onsite_feed_token"),
        )
    if not has_table("booking_onsite_pings"):
        op.create_table(
            "booking_onsite_pings",
            sa.Column("resource_id", sa.Integer(), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["booking_resources.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("resource_id", "day"),
        )


def downgrade():
    for table in ("booking_onsite_pings", "booking_onsite_feeds"):
        if has_table(table):
            op.drop_table(table)
    have = columns("booking_onsite")
    if "joins_id" in have:
        op.drop_constraint(
            "fk_booking_onsite_joins", "booking_onsite", type_="foreignkey"
        )
    if "series" in have:
        op.drop_index("ix_booking_onsite_series", "booking_onsite")
    for name, _ in reversed(NEW):
        if name in have:
            op.drop_column("booking_onsite", name)
