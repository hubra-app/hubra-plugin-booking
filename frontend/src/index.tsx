import { registerPlugin } from '@hubra/plugin-sdk'
import { IconCalendarTime } from '@tabler/icons-react'
import { BookingScreen } from './BookingScreen'
import { ItemBookingPanel } from './ItemBookingPanel'
import translations from './translations.json'

registerPlugin({
  id: 'booking',
  routes: [
    { path: 'booking', module: 'booking', component: BookingScreen },
    { path: 'booking/onsite', module: 'booking', component: BookingScreen },
    { path: 'booking/mine', module: 'booking', component: BookingScreen },
    { path: 'booking/requests', module: 'booking', perm: 'booking.bookings.update', component: BookingScreen },
    { path: 'booking/resources', module: 'booking', perm: 'booking.resources.update', component: BookingScreen },
  ],
  // On an inventory item's page: make it bookable, its fees and approval,
  // and a link to its calendar.
  slots: [{ slot: 'inventory.item', module: 'booking', component: ItemBookingPanel }],
  // The nav entry in hubra_booking/__init__.py names this icon.
  icons: { 'calendar-time': IconCalendarTime },
  translations,
})
