"""What Booking offers others (docs/contracts.md in hubra-app/hubra).

``booking.onsite.today``: in the morning, who said they'll be in which room
today (Vor Ort). Sent once a day, only when someone is coming. The Discord
plugin posts it in the channel the club picked.
"""

from __future__ import annotations

from pydantic import BaseModel


class OnsitePerson(BaseModel):
    member_id: int
    name: str
    # going (Komme), maybe (Vielleicht), here (Bin da)
    status: str
    starts: str | None = None  # "18:00", club time
    ends: str | None = None
    key_holder: bool = False
    comment: str | None = None


class OnsiteRoom(BaseModel):
    resource_id: int
    name: str
    location: str | None = None
    people: list[OnsitePerson]


class OnsiteToday(BaseModel):
    day: str  # YYYY-MM-DD
    rooms: list[OnsiteRoom]
    link: str  # the Vor Ort page in the club app
