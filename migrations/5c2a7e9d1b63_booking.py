"""booking resources and bookings

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_booking). has_table() keeps it safe to run twice.

Revision ID: 5c2a7e9d1b63
Revises:
Create Date: 2026-11-05 14:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "5c2a7e9d1b63"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _member(name):
    return sa.Column(name, sa.Integer(), nullable=True)


def _member_fk(name):
    return sa.ForeignKeyConstraint([name], ["members.id"], ondelete="SET NULL")


def upgrade():
    if not has_table("booking_resources"):
        op.create_table(
            "booking_resources",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("location", sa.String(200), nullable=True),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("inventory_item_id", sa.Integer(), nullable=True),
            sa.Column("needs_approval", sa.Boolean(), nullable=False),
            sa.Column("fee_flat", sa.Numeric(12, 2), nullable=True),
            sa.Column("fee_per_hour", sa.Numeric(12, 2), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("max_hours", sa.Integer(), nullable=True),
            sa.Column("advance_days", sa.Integer(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            _ts("created_at", nullable=False),
            sa.ForeignKeyConstraint(
                ["category_id"], ["transaction_categories.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("booking_bookings"):
        op.create_table(
            "booking_bookings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("resource_id", sa.Integer(), nullable=False),
            _member("member_id"),
            sa.Column("title", sa.String(200), nullable=True),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("series_id", sa.String(36), nullable=True),
            sa.Column("fee", sa.Numeric(12, 2), nullable=True),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            _member("decided_by"),
            _ts("decided_at"),
            sa.Column("decision_note", sa.String(500), nullable=True),
            _member("created_by"),
            _ts("created_at", nullable=False),
            sa.ForeignKeyConstraint(
                ["resource_id"], ["booking_resources.id"], ondelete="CASCADE"
            ),
            _member_fk("member_id"),
            _member_fk("decided_by"),
            _member_fk("created_by"),
            sa.ForeignKeyConstraint(
                ["invoice_id"], ["invoices.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_booking_bookings_resource_start",
            "booking_bookings",
            ["resource_id", "starts_at"],
        )
        op.create_index(
            "ix_booking_bookings_member_id", "booking_bookings", ["member_id"]
        )


def downgrade():
    for table in ("booking_bookings", "booking_resources"):
        if has_table(table):
            op.drop_table(table)
