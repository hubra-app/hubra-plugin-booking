"""Bell notifications in each member's language."""

from __future__ import annotations

from sqlalchemy import select

from hubra.core.extensions import db
from hubra.core.models.member import Member


def _german(member: Member) -> bool:
    return (getattr(member, "language", None) or "de").lower().startswith("de")


def notify(member_ids, texts, link: str) -> int:
    """*texts* is a function of ``german: bool`` returning ``(title, message)``.
    About a member's own money, so it always comes (no topic to turn off)."""
    from hubra.core.models.notification import Notification

    ids = sorted({m for m in member_ids if m})
    if not ids:
        return 0
    sent = 0
    for member in db.session.scalars(
        select(Member)
        .where(Member.id.in_(ids))
        .where(Member.status == "active")
        .where(Member.archived_at.is_(None))
    ):
        title, msg = texts(_german(member))
        db.session.add(
            Notification(
                member_id=member.id,
                kind="info",
                title=title[:255],
                msg=msg[:255],
                link=link,
            )
        )
        sent += 1
    return sent
