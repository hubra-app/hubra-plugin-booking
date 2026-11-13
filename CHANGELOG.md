# Booking

## Unreleased

- **Fees are open items**: a confirmed booking's fee goes to Finanzen as an open item (`finance.open_item.add`, hubra#337). With Finanzen › Einstellungen › Kleine Posten sammeln on, it waits for the member's next collected invoice (one invoice per month or quarter for the drinks tab, bookings and the rest); with it off it gets an invoice of its own straight away, as before (due in 30 days, not before the booking). A cancelled booking takes its fee back while it isn't billed, deletes its own unpaid invoice as before, and leaves an item that is already on a collected invoice for the treasurer. On a Hubra without open items it invoices as before. Needs Hubra 0.2.6 or later for open items.
- **Booking and Vor Ort live under Kalender**: Hubra's club calendar has them as tabs, **Vor Ort** (/app/calendar/onsite) and **Buchungen** (/app/calendar/bookings, with links to Meine Buchungen, Anfragen and Ressourcen), and its **Alles** view shows the bookings (pending ones marked with (?)) and one entry per room and day that someone comes on site. /app/booking, /app/booking/onsite and Anlässe › Vor Ort forward there. Needs the Hubra release with the club calendar tabs (`calendar.items`, tab screen `calendar`); raise `hubra:` in plugin.yaml to it when releasing.
- **Waiting requests are limited**: a member may have at most 5 bookings
  waiting for approval at once (setting «Offene Anfragen pro Mitglied»,
  0 = no limit); the board isn't limited. Each one holds its slot, so one
  member could otherwise block a resource with requests.
- The inventory picker and the item panel read items with the caller's own
  Inventory rights (managing resources isn't a right to read the inventory).
- Saving the same Vor Ort day twice at once no longer ends in an error.
- **Security fixes** (audit 2026-11-11): approving or cancelling a booking
  locks it, so two clicks at once can't bill twice; a member's series
  cancel checks every booking before withdrawing any invoice; the panel on
  an inventory item's page shows an item that isn't a resource only to
  those who may read the inventory; a resource colour is a palette name or
  a #hex code; the Vor Ort calendar feed drops control characters from
  names and comments and stops for members whose roles no longer include
  Booking. A deleted member leaves no Vor Ort days, watches or feed token
  behind, and their name and note go from bookings (the hourly job; club
  schemas made by cloning have no foreign keys that would cascade).
  Deleting a resource deletes its Vor Ort rows too.
- Booking dialog: Ablehnen or Buchung absagen as red text at the left, then Schliessen, then Bestätigen. Resource fees use the app's money field (CHF, 2 decimals, no arrows); "Zum Inventar" is a themed link.
- **Vor Ort moved to Anlässe**: it is a tab of the Anlässe page now
  (/app/operations/events/onsite), next to the club's events, instead of its
  own sidebar entry. Old links (/app/booking/onsite, reminders, the room QR
  check-in) lead there. A club without the events module keeps Vor Ort as a
  tab of Reservationen. Needs a Hubra version that shows plugin tabs on
  Anlässe (hubra-app/hubra#299); raise `hubra:` at release.
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
- **Vor Ort, repeat:** "Jeden Dienstag wiederholen bis …" adds the same entry
  every week (up to a year). Removing one offers "only this day" or "this and
  all following".
- **Vor Ort, Jetzt da:** a strip at the top shows who has checked in today
  (Bin da) per room and who has the key; "Ich gehe" checks out. An entry with
  an end time drops off after it.
- **Vor Ort, filters:** on the phone the week can show only days with people
  or only my days; "Nur meine" also filters the next two weeks.
- **Vor Ort, calendar feed:** "Kalender-Abo" gives a secret iCal address
  (renewable) with my days and the days others come to rooms I watch, for
  Google, Apple or Outlook.
- **Vor Ort, who brings the key?** The evening before, when people come to a
  room but nobody said they bring the key, the members who brought its key in
  the last half year are asked (once per room and day).
- **Vor Ort, Mitmachen:** "Andere dürfen mitmachen" on an entry shows a
  "Mitmachen" button to others; joining tells the member and shows "mit …"
  and how many join.
- **Vor Ort, Statistik** (for those who manage resources or bookings): visits,
  days and people per room and month, and visits per weekday.
- Needs `flask db upgrade` (migration 6a1c4e8b2d90: new columns on
  booking_onsite, tables booking_onsite_feeds and booking_onsite_pings).

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
