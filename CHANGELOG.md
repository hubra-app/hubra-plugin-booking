# Booking

## Unreleased

- **Vor Ort** on the phone shows the whole week or month (not only one day),
  one room at a time: pick the room at the top. The week lists its seven
  days with who comes; the month shows how many come and the key, and a day
  opens its week. On a wide screen the
  week shows today's column and how many come each day, and the room column
  stays in view when scrolling sideways.
- **Vor Ort** lists the next 2 weeks under the calendar: a card per day with
  who comes to which room, times and comments, the key, and "Ich auch".
- **Vor Ort** has its own sidebar entry (Erweiterungen › Vor Ort), so members
  find it without opening Reservationen first. Hubra puts "Heute vor Ort" on
  the built-in Dashboard › Persönlich while Booking is on.
- German: "z. B." with a space; the reminder hint points at Konto › Mitgliedschaft › Benachrichtigungen, where that setting is.

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Mitglied Ansehen, Vorstand Bearbeiten. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.
- **Vor Ort** (new tab): members say on which days they'll be in a room
  (Komme, Vielleicht, Bin da for today), with an optional time and comment
  and "Ich bringe den Schlüssel", so others can come on the same days.
  Nothing is reserved and there is no cap. Week grid (rooms by days, a day on
  the phone) and a month view with counts per room; "Ich komme auch" in one
  tap; exclusive bookings of the room show as "Belegt". Members can watch a
  room (bell when someone plans to come). The evening before (18:00), everyone
  who said Komme or Vielleicht gets a reminder with who else comes and who
  brings the key: bell and Discord DM by the member's "Erinnerung vor
  Anlässen" choices, mail by their reminder mail switch. In the morning
  (07:00) the day's list goes out as the new event `booking.onsite.today`
  (the Discord plugin posts it). Entries are kept at least 365 days
  (settings `onsite_keep_days`, `onsite_reminder_hour`, `onsite_today_hour`).
  New tables `booking_onsite`, `booking_onsite_watches`,
  `booking_onsite_days` (migration 8e3b6d1a4f27); hourly job
  `booking-onsite-hourly`; `uses` adds `jobs` and `settings`.
- **Booking now needs Inventory** (2.1 or newer) and is shown as its add-on:
  `requires: [inventory, …]`, `depends: inventory`. New equipment is made
  bookable on the item's page; Booking's own form adds rooms.
- Equipment comes from the inventory: with the Inventory plugin running, a
  new equipment resource is picked from its items instead of typed in, and
  its name and place follow the item. Each item is at most one resource; a
  room may be linked to an item too. Items out of use (maintenance, broken,
  lost, retired, archived) can't be booked, and a deleted item switches its
  resource off (event `inventory.item.deleted`). Without Inventory,
  resources are typed in as before.
- A "Reservationen" panel on an inventory item's page (slot `inventory.item`):
  managers make the item bookable there and set fee, approval and limits;
  members see the terms and a link to its calendar
  (`/app/booking?resource=<id>`). New route `GET /resources/by-item/<id>`.
  The Booking picker no longer lists items that already are a resource, and
  equipment cards in Booking open the item's page.
- Inventory items are read through Inventory's contracts
  (`inventory.items.get`, `inventory.items.list`) instead of its table. Without
  Inventory, or with it switched off, resources simply have no linked item.
  Needs Hubra with contracts (hubra-app/hubra#231).

## 1.0.0

First version: rooms and equipment on a week calendar, overlaps refused,
approval where a resource needs it, fees on the member's invoice, weekly
series for the board, and an optional link to an Inventory item.
