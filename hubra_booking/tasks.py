"""Celery task: Vor Ort's hourly work (onsite.py)."""

from __future__ import annotations

from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app


@celery_app.task(name="hubra_booking.tasks.onsite_hourly")
@per_tenant_job("booking")
def onsite_hourly() -> dict:
    from hubra.core.extensions import db

    from . import onsite

    done = {
        "purged": onsite.purge(),
        **onsite.remind(),
        **onsite.announce(),
    }
    db.session.commit()
    return done
