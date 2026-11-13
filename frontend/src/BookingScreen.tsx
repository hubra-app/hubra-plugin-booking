import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button, Group } from '@mantine/core'
import { IconCalendarTime, IconChecklist, IconList, IconSettings } from '@tabler/icons-react'
import { ErrorBanner, LoadingSpinner, PageHead, Tabs, useT } from '@hubra/plugin-sdk'
import { QK, errorText, getOptions } from './api'
import { CalendarTab } from './CalendarTab'
import { MineTab, RequestsTab } from './ListsTab'
import { OnsiteTab } from './OnsiteTab'
import { ResourcesTab } from './ResourcesTab'

/** Vor Ort as a tab of Kalender (registered in index.tsx): who is in which room on which day. */
export function CalendarOnsiteTab() {
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const can = options.data?.can
  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />
  return <OnsiteTab canManage={!!can?.resources} canStats={!!(can?.resources || can?.bookings)} />
}

/**
 * The booking calendar as a tab of Kalender (registered in index.tsx), with
 * the way to the member's own bookings, the requests and the resources.
 */
export function CalendarBookingsTab() {
  const { t } = useT()
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const can = options.data?.can
  const pending = options.data?.pending ?? 0
  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />
  return (
    <>
      <Group gap="xs" mb="sm" justify="flex-end" wrap="wrap">
        <Button component={Link} to="/app/booking/mine" variant="default" size="xs" leftSection={<IconList size={14} />}>
          {t('booking.tabs.mine')}
        </Button>
        {can?.bookings && (
          <Button component={Link} to="/app/booking/requests" variant="default" size="xs" leftSection={<IconChecklist size={14} />}>
            {pending ? `${t('booking.tabs.requests')} (${pending})` : t('booking.tabs.requests')}
          </Button>
        )}
        {can?.resources && (
          <Button component={Link} to="/app/booking/resources" variant="default" size="xs" leftSection={<IconSettings size={14} />}>
            {t('booking.tabs.resources')}
          </Button>
        )}
      </Group>
      <CalendarTab options={options.data} />
    </>
  )
}

/** The old addresses /app/booking/onsite (links in reminders, mails) go on working. */
export function OnsiteRedirect() {
  const location = useLocation()
  return <Navigate to={`/app/calendar/onsite${location.search}`} replace />
}

/**
 * Booking: the caller's bookings, requests and resources. The calendar itself
 * is a tab of Kalender; /app/booking (and its ?resource= links) lead there.
 */
export function BookingScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const location = useLocation()
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const can = options.data?.can
  const pending = options.data?.pending ?? 0
  const part = location.pathname.split('/app/booking')[1]?.replace(/^\//, '').split('/')[0] ?? ''
  const tabs = [
    { id: 'calendar', label: t('booking.tabs.calendar'), icon: <IconCalendarTime size={16} />, show: true },
    { id: 'mine', label: t('booking.tabs.mine'), icon: <IconList size={16} />, show: true },
    {
      id: 'requests',
      label: pending ? `${t('booking.tabs.requests')} (${pending})` : t('booking.tabs.requests'),
      icon: <IconChecklist size={16} />,
      show: !!can?.bookings,
    },
    { id: 'resources', label: t('booking.tabs.resources'), icon: <IconSettings size={16} />, show: !!can?.resources },
  ].filter((tb) => tb.show)
  const active = tabs.find((tb) => tb.id === part)?.id ?? 'calendar'

  if (active === 'calendar') return <Navigate to={`/app/calendar/bookings${location.search}`} replace />
  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />

  return (
    <>
      <PageHead title={t('booking.title')} desc={t('booking.desc')} />
      <Tabs tabs={tabs} activeTab={active} onTabChange={(id) => navigate(id === 'calendar' ? '/app/calendar/bookings' : `/app/booking/${id}`)} />
      {active === 'mine' && <MineTab options={options.data} />}
      {active === 'requests' && <RequestsTab options={options.data} />}
      {active === 'resources' && <ResourcesTab options={options.data} />}
    </>
  )
}
