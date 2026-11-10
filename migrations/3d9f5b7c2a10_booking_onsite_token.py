"""booking: a secret per room for Vor Ort check-in by QR code

Revision ID: 3d9f5b7c2a10
Revises: 8e3b6d1a4f27
Create Date: 2026-11-10 07:00:00

"""

import sqlalchemy as sa
from alembic import op

from hubra.core.plugins.ops import columns

revision = "3d9f5b7c2a10"
down_revision = "8e3b6d1a4f27"
branch_labels = None
depends_on = None


def upgrade():
    have = columns("booking_resources")
    if have and "onsite_token" not in have:
        op.add_column(
            "booking_resources", sa.Column("onsite_token", sa.String(43), nullable=True)
        )


def downgrade():
    if "onsite_token" in columns("booking_resources"):
        op.drop_column("booking_resources", "onsite_token")
