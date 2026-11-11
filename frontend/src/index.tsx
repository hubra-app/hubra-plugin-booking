import { registerPlugin } from '@hubra/plugin-sdk'
import { IconCalendarTime, IconMapPin } from '@tabler/icons-react'
import { BookingScreen } from './BookingScreen'
import { CheckinScreen } from './CheckinScreen'
import { OnsiteEventsTab, OnsiteRoute } from './OnsitePage'
import { ItemBookingPanel } from './ItemBookingPanel'
import translations from './translations.json'

registerPlugin({
  id: 'booking',
  routes: [
    { path: 'booking', module: 'booking', component: BookingScreen },
    // Old links (notifications, Discord, widgets) lead to Vor Ort on Anlässe.
    { path: 'booking/onsite', module: 'booking', component: OnsiteRoute },
    // A room's QR code: scanning it checks the member in (Vor Ort, Bin da).
    { path: 'booking/checkin/:token', module: 'booking', component: CheckinScreen },
    { path: 'booking/mine', module: 'booking', component: BookingScreen },
    { path: 'booking/requests', module: 'booking', perm: 'booking.bookings.update', component: BookingScreen },
    { path: 'booking/resources', module: 'booking', perm: 'booking.resources.update', component: BookingScreen },
  ],
  // Vor Ort: a tab on Anlässe, next to the club's events (hubra >= the
  // release with the "events" tab screen).
  tabs: [{ screen: 'events', id: 'onsite', module: 'booking', label: 'booking.tabs.onsite', component: OnsiteEventsTab }],
  // On an inventory item's page: make it bookable, its fees and approval,
  // and a link to its calendar.
  slots: [{ slot: 'inventory.item', module: 'booking', component: ItemBookingPanel }],
  // The nav entries in hubra_booking/__init__.py name these icons.
  icons: { 'calendar-time': IconCalendarTime, 'map-pin': IconMapPin },
  translations,
})
