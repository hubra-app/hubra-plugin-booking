import { registerPlugin } from '@hubra/plugin-sdk'
import { IconCalendarTime, IconMapPin } from '@tabler/icons-react'
import { BookingScreen, CalendarBookingsTab, CalendarOnsiteTab, OnsiteRedirect } from './BookingScreen'
import { CheckinScreen } from './CheckinScreen'
import { ItemBookingPanel } from './ItemBookingPanel'
import translations from './translations.json'

registerPlugin({
  id: 'booking',
  routes: [
    { path: 'booking', module: 'booking', component: BookingScreen },
    // Vor Ort lives on Anlässe now; the old address still leads there.
    { path: 'booking/onsite', module: 'booking', component: OnsiteRedirect },
    // A room's QR code: scanning it checks the member in (Vor Ort, Bin da).
    { path: 'booking/checkin/:token', module: 'booking', component: CheckinScreen },
    { path: 'booking/mine', module: 'booking', component: BookingScreen },
    { path: 'booking/requests', module: 'booking', perm: 'booking.bookings.update', component: BookingScreen },
    { path: 'booking/resources', module: 'booking', perm: 'booking.resources.update', component: BookingScreen },
  ],
  // Both calendars live under Kalender, next to the club's other dates:
  // Vor Ort (who is in which room on which day, /app/calendar/onsite) and the
  // booking calendar (/app/calendar/bookings).
  tabs: [
    { screen: 'calendar', id: 'onsite', label: 'booking.tabs.onsite', module: 'booking', component: CalendarOnsiteTab },
    { screen: 'calendar', id: 'bookings', label: 'booking.tabs.bookings', module: 'booking', component: CalendarBookingsTab },
  ],
  // On an inventory item's page: make it bookable, its fees and approval,
  // and a link to its calendar.
  slots: [{ slot: 'inventory.item', module: 'booking', component: ItemBookingPanel }],
  // The nav entries in hubra_booking/__init__.py name these icons.
  icons: { 'calendar-time': IconCalendarTime, 'map-pin': IconMapPin },
  translations,
})
