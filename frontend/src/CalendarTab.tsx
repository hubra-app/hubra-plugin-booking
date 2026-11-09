import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ActionIcon, Badge, Box, Button, Group, Paper, ScrollArea, Select, Stack, Text } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconChevronLeft, IconChevronRight, IconPlus, IconCalendarOff } from '@tabler/icons-react'
import { EmptyState, ErrorBanner, LoadingSpinner, useT } from '@hubra/plugin-sdk'
import {
  QK,
  addDays,
  errorText,
  hhmm,
  isoDay,
  listCalendar,
  listResources,
  parseLocal,
  weekStart,
  type Booking,
  type Options,
  type Resource,
} from './api'
import { BookingDetail, BookingModal } from './BookingModal'
import { chf } from './common'

const FIRST = 7
const LAST = 23
const ROW = 32

export function resourceColor(r: Resource | undefined) {
  return r?.color || 'violet'
}

/** The week (or, on a phone, the day) of one resource. */
export function CalendarTab({ options }: { options: Options | undefined }) {
  const { t, i18n } = useT()
  const phone = useMediaQuery('(max-width: 48em)')
  const resources = useQuery({ queryKey: QK.resources(false), queryFn: () => listResources() })
  const [picked, setPicked] = useState<number | null>(() => {
    // ?resource=<id>: opened from an inventory item's page.
    const asked = Number(new URLSearchParams(window.location.search).get('resource'))
    if (asked) return asked
    try {
      return Number(localStorage.getItem('booking.resource')) || null
    } catch {
      return null
    }
  })
  const pick = (id: number | null) => {
    setPicked(id)
    try {
      if (id) localStorage.setItem('booking.resource', String(id))
    } catch {
      /* private mode */
    }
  }
  const [anchor, setAnchor] = useState(() => new Date())
  const [creating, setCreating] = useState<{ start: string; end: string } | null>(null)
  const [open, setOpen] = useState<Booking | null>(null)

  const days = useMemo(() => {
    if (phone) {
      const d = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate())
      return [d]
    }
    const first = weekStart(anchor)
    return Array.from({ length: 7 }, (_, i) => addDays(first, i))
  }, [anchor, phone])
  const from = isoDay(days[0])
  const to = isoDay(addDays(days[days.length - 1], 1))
  const bookings = useQuery({ queryKey: QK.calendar(from, to), queryFn: () => listCalendar(from, to) })

  const list = resources.data ?? []
  const resource = list.find((r) => r.id === picked) ?? list[0]
  const shown = (bookings.data ?? []).filter((b) => b.resourceId === resource?.id)
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'
  const today = isoDay(new Date())

  if (resources.error) return <ErrorBanner message={errorText(resources.error)} onRetry={() => resources.refetch()} />
  if (resources.isLoading) return <LoadingSpinner />
  if (!list.length)
    return (
      <EmptyState
        icon={<IconCalendarOff size={28} />}
        title={t('booking.calendar.noResources')}
        description={options?.can.resources ? t('booking.calendar.noResourcesHint') : undefined}
      />
    )

  const step = phone ? 1 : 7
  const rangeLabel = phone
    ? days[0].toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
    : `${days[0].toLocaleDateString(locale, { day: 'numeric', month: 'short' })} – ${days[6].toLocaleDateString(locale, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })}`

  const slot = (day: Date, hour: number) => {
    const d = isoDay(day)
    const h = (n: number) => `${String(Math.min(n, 23)).padStart(2, '0')}:${n > 23 ? '59' : '00'}`
    setCreating({ start: `${d}T${h(hour)}`, end: `${d}T${h(hour + 1)}` })
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm" wrap="wrap">
          <Select
            aria-label={t('booking.resource')}
            data={list.map((r) => ({ value: String(r.id), label: r.name }))}
            value={resource ? String(resource.id) : null}
            onChange={(v) => pick(v ? Number(v) : null)}
            allowDeselect={false}
            w={220}
          />
          <Group gap={4} wrap="nowrap">
            <ActionIcon variant="default" size="lg" aria-label={t('booking.calendar.prev')} onClick={() => setAnchor(addDays(anchor, -step))}>
              <IconChevronLeft size={16} />
            </ActionIcon>
            <Button variant="default" onClick={() => setAnchor(new Date())}>
              {t('booking.calendar.today')}
            </Button>
            <ActionIcon variant="default" size="lg" aria-label={t('booking.calendar.next')} onClick={() => setAnchor(addDays(anchor, step))}>
              <IconChevronRight size={16} />
            </ActionIcon>
          </Group>
          <Text fw={600}>{rangeLabel}</Text>
        </Group>
        <Button leftSection={<IconPlus size={16} />} onClick={() => slot(days[0] < new Date() ? new Date() : days[0], 18)}>
          {t('booking.new')}
        </Button>
      </Group>
      {resource && <ResourceLine resource={resource} />}
      {bookings.error ? (
        <ErrorBanner message={errorText(bookings.error)} onRetry={() => bookings.refetch()} />
      ) : (
        <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
          <ScrollArea type="auto">
            <Box style={{ minWidth: phone ? undefined : 760 }}>
              <Box style={{ display: 'grid', gridTemplateColumns: `48px repeat(${days.length}, 1fr)`, borderBottom: '1px solid var(--mantine-color-default-border)' }}>
                <div />
                {days.map((d) => (
                  <Box key={isoDay(d)} py={6} ta="center" style={{ borderLeft: '1px solid var(--mantine-color-default-border)' }}>
                    <Text size="xs" c="dimmed" tt="uppercase">
                      {d.toLocaleDateString(locale, { weekday: 'short' })}
                    </Text>
                    <Text fw={isoDay(d) === today ? 700 : 500} c={isoDay(d) === today ? 'violet' : undefined}>
                      {d.getDate()}
                    </Text>
                  </Box>
                ))}
              </Box>
              <Box style={{ display: 'grid', gridTemplateColumns: `48px repeat(${days.length}, 1fr)` }}>
                <Box>
                  {Array.from({ length: LAST - FIRST }, (_, i) => (
                    <Text key={i} size="xs" c="dimmed" ta="right" pr={6} style={{ height: ROW, lineHeight: '14px' }}>
                      {String(FIRST + i).padStart(2, '0')}:00
                    </Text>
                  ))}
                </Box>
                {days.map((d) => (
                  <DayColumn
                    key={isoDay(d)}
                    day={d}
                    bookings={shown}
                    color={resourceColor(resource)}
                    onSlot={(h) => slot(d, h)}
                    onOpen={setOpen}
                  />
                ))}
              </Box>
            </Box>
          </ScrollArea>
        </Paper>
      )}
      {bookings.isLoading && <LoadingSpinner />}
      {creating && (
        <BookingModal
          options={options}
          resources={list}
          resourceId={resource?.id ?? null}
          start={creating.start}
          end={creating.end}
          onClose={() => setCreating(null)}
        />
      )}
      {open && <BookingDetail booking={open} options={options} onClose={() => setOpen(null)} />}
    </Stack>
  )
}

function ResourceLine({ resource }: { resource: Resource }) {
  const { t } = useT()
  const fee = [
    resource.feeFlat ? chf(resource.feeFlat) : null,
    resource.feePerHour ? t('booking.perHour', { amount: chf(resource.feePerHour) }) : null,
  ]
    .filter(Boolean)
    .join(' + ')
  return (
    <Group gap="xs" wrap="wrap">
      <Badge variant="light" color={resourceColor(resource)} style={{ textTransform: 'none' }}>
        {t(`booking.kinds.${resource.kind}`)}
      </Badge>
      {resource.location && (
        <Text size="sm" c="dimmed">
          {resource.location}
        </Text>
      )}
      {resource.needsApproval && (
        <Badge variant="light" color="orange" style={{ textTransform: 'none' }}>
          {t('booking.needsApproval')}
        </Badge>
      )}
      <Text size="sm" c="dimmed">
        {fee || t('booking.free')}
        {resource.maxHours ? ` · ${t('booking.maxHours', { count: resource.maxHours })}` : ''}
      </Text>
    </Group>
  )
}

function DayColumn({
  day,
  bookings,
  color,
  onSlot,
  onOpen,
}: {
  day: Date
  bookings: Booking[]
  color: string
  onSlot: (hour: number) => void
  onOpen: (b: Booking) => void
}) {
  const { t } = useT()
  const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate(), FIRST)
  const dayEnd = new Date(day.getFullYear(), day.getMonth(), day.getDate(), LAST)
  const now = new Date()
  const blocks = bookings
    .map((b) => {
      const s = parseLocal(b.startsAt)
      const e = parseLocal(b.endsAt)
      if (e <= dayStart || s >= dayEnd) return null
      const top = ((Math.max(s.getTime(), dayStart.getTime()) - dayStart.getTime()) / 3_600_000) * ROW
      const bottom = ((Math.min(e.getTime(), dayEnd.getTime()) - dayStart.getTime()) / 3_600_000) * ROW
      return { b, top, height: Math.max(bottom - top, 18) }
    })
    .filter((x): x is { b: Booking; top: number; height: number } => x !== null)

  return (
    <Box style={{ position: 'relative', borderLeft: '1px solid var(--mantine-color-default-border)' }}>
      {Array.from({ length: LAST - FIRST }, (_, i) => {
        const past = new Date(day.getFullYear(), day.getMonth(), day.getDate(), FIRST + i + 1) <= now
        return (
          <Box
            key={i}
            onClick={past ? undefined : () => onSlot(FIRST + i)}
            style={{
              height: ROW,
              borderTop: i ? '1px solid var(--mantine-color-default-border)' : undefined,
              cursor: past ? 'default' : 'pointer',
              background: past ? 'var(--mantine-color-default-hover)' : undefined,
            }}
          />
        )
      })}
      {blocks.map(({ b, top, height }) => {
        const pending = b.status === 'pending'
        return (
          <Box
            key={b.id}
            role="button"
            tabIndex={0}
            onClick={() => onOpen(b)}
            onKeyDown={(e) => e.key === 'Enter' && onOpen(b)}
            px={6}
            py={2}
            style={{
              position: 'absolute',
              top: top + 1,
              left: 3,
              right: 3,
              height: height - 2,
              overflow: 'hidden',
              cursor: 'pointer',
              borderRadius: 6,
              background: `linear-gradient(var(--mantine-color-${color}-light), var(--mantine-color-${color}-light)), var(--mantine-color-body)`,
              borderLeft: `3px ${pending ? 'dashed' : 'solid'} var(--mantine-color-${color}-filled)`,
              opacity: pending ? 0.75 : 1,
            }}
          >
            {height > 36 ? (
              <>
                <Text size="xs" fw={600} lh={1.3} truncate>
                  {b.title || b.memberName}
                </Text>
                <Text size="xs" c="dimmed" lh={1.3} truncate>
                  {hhmm(b.startsAt)}–{hhmm(b.endsAt)}
                  {pending ? ` · ${t('booking.status.pending')}` : b.title && b.memberName ? ` · ${b.memberName}` : ''}
                </Text>
              </>
            ) : (
              <Text size="xs" fw={600} lh={1.3} truncate>
                {hhmm(b.startsAt)} {b.title || b.memberName}
              </Text>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
