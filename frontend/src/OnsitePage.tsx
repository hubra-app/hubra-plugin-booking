import { Navigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ErrorBanner, LoadingSpinner, useModules } from '@hubra/plugin-sdk'
import { QK, errorText, getOptions } from './api'
import { BookingScreen } from './BookingScreen'
import { OnsiteTab } from './OnsiteTab'

/** Vor Ort as a tab on Anlässe (screen "events"), with the caller's rights. */
export function OnsiteEventsTab() {
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const can = options.data?.can
  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />
  return <OnsiteTab canManage={!!can?.resources} canStats={!!(can?.resources || can?.bookings)} />
}

/**
 * The old address /app/booking/onsite, which notifications, the daily
 * Discord post and the dashboard widgets link to: Vor Ort sits on Anlässe
 * when the club has the events module, otherwise it stays a Booking tab.
 */
export function OnsiteRoute() {
  const { canUse } = useModules()
  const location = useLocation()
  if (canUse('events')) return <Navigate to={`/app/operations/events/onsite${location.search}`} replace />
  return <BookingScreen />
}
