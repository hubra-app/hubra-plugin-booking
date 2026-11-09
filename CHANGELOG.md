# Booking

## Unreleased

- Equipment comes from the inventory: with the Inventory plugin running, a
  new equipment resource is picked from its items instead of typed in, and
  its name and place follow the item. Each item is at most one resource; a
  room may be linked to an item too. Items out of use (maintenance, broken,
  lost, retired, archived) can't be booked, and a deleted item switches its
  resource off (event `inventory.item.deleted`). Without Inventory,
  resources are typed in as before.
- Inventory items are read through Inventory's contracts
  (`inventory.items.get`, `inventory.items.list`) instead of its table. Without
  Inventory, or with it switched off, resources simply have no linked item.
  Needs Hubra with contracts (hubra-app/hubra#231).

## 1.0.0

First version: rooms and equipment on a week calendar, overlaps refused,
approval where a resource needs it, fees on the member's invoice, weekly
series for the board, and an optional link to an Inventory item.
