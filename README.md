# Booking

[![Test and release](https://github.com/hubra-app/hubra-plugin-booking/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/hubra-app/hubra-plugin-booking/actions/workflows/release.yml?query=branch%3Amain) [![Release](https://img.shields.io/github/v/release/hubra-app/hubra-plugin-booking)](https://github.com/hubra-app/hubra-plugin-booking/releases/latest) [![License: all rights reserved](https://img.shields.io/badge/license-all%20rights%20reserved-lightgrey)](LICENSE)

A plugin for [Hubra](https://hubra.club). Rooms and equipment on a calendar: members book a slot, overlapping bookings are refused, the board approves where a resource needs it, and a fee goes on the member's invoice.

**Version** 1.0.0 · **Works with** Hubra >=0.2,<1 · **Plugin id** `booking` · **Needs** the members and finance modules; links to the Inventory plugin when the club runs it

![Calendar](docs/screenshots/calendar.png)

## What it does

| Tab | |
| --- | --- |
| Kalender | The week of one resource (a day on the phone). Click a free hour to book it. Bookings show the title or the member's name; requests still waiting for approval are dashed and already hold the slot. |
| Meine Buchungen | The member's upcoming bookings and the last 30 days. A member cancels their own booking until it starts; an unpaid fee invoice goes with it. |
| Anfragen | Requests waiting for approval. Confirming one bills the fee; the member gets a bell notification either way. |
| Ressourcen | Rooms and equipment with a colour, a place, a fee per booking and/or per hour (with a finance category), the longest booking, how far ahead members can book, an approval switch and an optional Inventory item. |

Approvers can book for another member and repeat a booking weekly (up to
52 weeks); cancelling one booking of a series can cancel the rest too.
Times are the club's wall-clock time (`MAIL_TIMEZONE`, Europe/Zurich by
default).

Permissions: `booking.resources.update`, `booking.bookings.update`. Every
member can see the calendar and book.

## Install

Platform admins install it from the plugin catalogue in the manager portal
(official Marketplace, <https://plugins.hubra.club/index.json>, signed with
the Hubra project key). Clubs then switch it on under Einstellungen → Module
& Plugins.

## Develop

Clone this repository into `plugins/booking` of a Hubra checkout. Its tests
then run with Hubra's (`cd app/backend && pytest ../../plugins/booking`), and
`npm run build:plugin` in `app/frontend` builds its frontend. The workflow
does the same against Hubra's `main` on every push and pull request.

## Releasing

Bump `version` in `plugin.yaml`, add a `## <version>` section to
`CHANGELOG.md`, commit, then publish a GitHub release tagged `v<version>`
(web UI, or `gh release create v<version> --target main --notes ""`). The
workflow tests the plugin and builds its frontend; a separate job in the
`plugin-signing` environment, the only one with the `HUBRA_SIGNING_KEY`
secret, signs it; then `booking-<version>.zip` is attached to the release. Files listed in `.releaseignore` stay out of the zip.

Source: <https://github.com/hubra-app/hubra-plugin-booking>
