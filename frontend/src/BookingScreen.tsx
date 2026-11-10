import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { IconCalendarTime, IconChecklist, IconList, IconMapPin, IconSettings } from '@tabler/icons-react'
import { ErrorBanner, LoadingSpinner, PageHead, Tabs, useT } from '@hubra/plugin-sdk'
import { QK, errorText, getOptions } from './api'
import { CalendarTab } from './CalendarTab'
import { MineTab, RequestsTab } from './ListsTab'
import { OnsiteTab } from './OnsiteTab'
import { ResourcesTab } from './ResourcesTab'

/** Booking: the calendar, Vor Ort, the caller's bookings, requests and resources. */
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
    { id: 'onsite', label: t('booking.tabs.onsite'), icon: <IconMapPin size={16} />, show: true },
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

  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />

  return (
    <>
      <PageHead title={t('booking.title')} desc={t('booking.desc')} />
      <Tabs tabs={tabs} activeTab={active} onTabChange={(id) => navigate(id === 'calendar' ? '/app/booking' : `/app/booking/${id}`)} />
      {active === 'calendar' && <CalendarTab options={options.data} />}
      {active === 'onsite' && <OnsiteTab />}
      {active === 'mine' && <MineTab options={options.data} />}
      {active === 'requests' && <RequestsTab options={options.data} />}
      {active === 'resources' && <ResourcesTab options={options.data} />}
    </>
  )
}
