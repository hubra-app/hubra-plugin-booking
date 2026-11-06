# Booking

## Unreleased

- Inventory items are read through Inventory's contracts
  (`inventory.items.get`, `inventory.items.list`) instead of its table. Without
  Inventory, or with it switched off, resources simply have no linked item.
  Needs Hubra with contracts (hubra-app/hubra#231).

## 1.0.0

First version: rooms and equipment on a week calendar, overlaps refused,
approval where a resource needs it, fees on the member's invoice, weekly
series for the board, and an optional link to an Inventory item.
