import { useMemo, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  Group,
  Paper,
  ScrollArea,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import {
  IconBell,
  IconBellOff,
  IconChevronLeft,
  IconChevronRight,
  IconDoorOff,
  IconKey,
  IconMapPin,
  IconPlus,
  IconPrinter,
  IconQrcode,
  IconRefresh,
} from '@tabler/icons-react'
import { EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import {
  QK,
  addDays,
  deleteOnsite,
  getOnsiteQr,
  renewOnsiteQr,
  errorText,
  hhmm,
  isoDay,
  listOnsite,
  setOnsite,
  watchOnsite,
  weekStart,
  type OnsiteData,
  type OnsiteEntry,
  type OnsiteStatus,
} from './api'
import { useAction } from './common'

type Room = OnsiteData['rooms'][number]

export const ONSITE_COLOR: Record<OnsiteStatus, string> = {
  going: 'green',
  maybe: 'yellow',
  here: 'violet',
}

function timeText(e: OnsiteEntry, t: (k: string, o?: Record<string, unknown>) => string) {
  if (e.from && e.to) return `${e.from}–${e.to}`
  if (e.from) return t('booking.onsite.fromTime', { time: e.from })
  if (e.to) return t('booking.onsite.untilTime', { time: e.to })
  return ''
}

/** How many are coming to a room (or to any room) on a day. */
function summary(entries: OnsiteEntry[], day: string, roomId?: number) {
  const people = entries.filter((e) => e.day === day && (roomId == null || e.resourceId === roomId))
  return {
    people,
    count: people.length,
    sure: people.some((e) => e.status !== 'maybe'),
    mine: people.some((e) => e.mine),
    key: people.some((e) => e.keyHolder),
  }
}

/** A small round count: violet when the caller is in, green when someone is
 * sure, yellow when all are maybe. */
function CountDot({ s, size = 'sm' }: { s: ReturnType<typeof summary>; size?: 'xs' | 'sm' }) {
  if (!s.count) return null
  return (
    <Badge
      size={size}
      circle
      variant={s.mine ? 'filled' : 'light'}
      color={s.mine ? 'violet' : s.sure ? 'green' : 'yellow'}
      title={s.people.map((e) => e.memberName).join(', ')}
    >
      {s.count}
    </Badge>
  )
}

const VIEW_KEY = 'booking.onsiteView'

/** Vor Ort: who plans to be in which room on which day. A week of days by
 * rooms or a month; on the phone the week or month is an overview and the
 * picked day's rooms show below it. Under the calendar, the next two weeks
 * as a list of days. */
export function OnsiteTab({ canManage = false }: { canManage?: boolean }) {
  const { t, i18n } = useT()
  const qc = useQueryClient()
  const phone = useMediaQuery('(max-width: 48em)')
  const { run } = useAction()
  // The picked day: the week or month around it is shown, and on the phone
  // its rooms are listed under the calendar.
  const [anchor, setAnchor] = useState(() => {
    const asked = new URLSearchParams(window.location.search).get('day')
    return asked ? new Date(`${asked}T12:00`) : new Date()
  })
  const [editing, setEditing] = useState<{ room: Room; day: string; entry?: OnsiteEntry } | null>(
    null,
  )
  const [qrFor, setQrFor] = useState<Room | null>(null)
  const [view, setView] = useState<'week' | 'month'>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === 'month' ? 'month' : 'week'
    } catch {
      return 'week'
    }
  })
  const pickView = (v: 'week' | 'month') => {
    setView(v)
    try {
      localStorage.setItem(VIEW_KEY, v)
    } catch {
      /* private mode */
    }
  }
  const month = view === 'month'

  const days = useMemo(() => {
    if (month) {
      // Whole weeks around the month: Monday before the 1st, six weeks.
      const first = weekStart(new Date(anchor.getFullYear(), anchor.getMonth(), 1))
      return Array.from({ length: 42 }, (_, i) => addDays(first, i))
    }
    const first = weekStart(anchor)
    return Array.from({ length: 7 }, (_, i) => addDays(first, i))
  }, [anchor, month])
  const from = isoDay(days[0])
  const to = isoDay(addDays(days[days.length - 1], 1))
  const data = useQuery({ queryKey: QK.onsite(from, to), queryFn: () => listOnsite(from, to) })
  const soonFrom = isoDay(new Date())
  const soonTo = isoDay(addDays(new Date(), NEXT_DAYS))
  const soon = useQuery({
    queryKey: QK.onsite(soonFrom, soonTo),
    queryFn: () => listOnsite(soonFrom, soonTo),
  })
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'
  const today = data.data?.today ?? isoDay(new Date())

  if (data.error)
    return <ErrorBanner message={errorText(data.error)} onRetry={() => data.refetch()} />
  if (data.isLoading || !data.data) return <LoadingSpinner />
  const { rooms, entries, busy, watching } = data.data
  if (!rooms.length)
    return (
      <EmptyState
        icon={<IconDoorOff size={28} />}
        title={t('booking.onsite.noRooms')}
        description={t('booking.onsite.noRoomsHint')}
      />
    )

  const picked = isoDay(anchor)
  const refresh = () => qc.invalidateQueries({ queryKey: ['booking', 'onsite'] })
  const quick = (room: Room, day: string, status: OnsiteStatus) =>
    run(() => setOnsite({ resourceId: room.id, day, status }), t('booking.onsite.saved')).then(
      (ok) => {
        if (ok) refresh()
      },
    )
  const toggleWatch = (room: Room) => {
    const on = !watching.includes(room.id)
    run(
      () => watchOnsite(room.id, on),
      on ? t('booking.onsite.watchOn', { room: room.name }) : t('booking.onsite.watchOff'),
    ).then((ok) => {
      if (ok) refresh()
    })
  }

  const shift = (n: number) =>
    setAnchor(
      month ? new Date(anchor.getFullYear(), anchor.getMonth() + n, 1) : addDays(anchor, n * 7),
    )
  const rangeLabel = month
    ? anchor.toLocaleDateString(locale, { month: 'long', year: 'numeric' })
    : `${days[0].toLocaleDateString(locale, { day: 'numeric', month: 'short' })} – ${days[6].toLocaleDateString(
        locale,
        phone
          ? { day: 'numeric', month: 'short' }
          : { day: 'numeric', month: 'short', year: 'numeric' },
      )}`

  const cell = (room: Room, d: Date) => {
    const day = isoDay(d)
    const people = entries.filter((e) => e.resourceId === room.id && e.day === day)
    const taken = busy.filter(
      (b) =>
        b.resourceId === room.id && b.startsAt.slice(0, 10) <= day && b.endsAt.slice(0, 10) >= day,
    )
    return (
      <Cell
        key={`${room.id}-${day}`}
        room={room}
        day={day}
        past={day < today}
        isToday={day === today}
        people={people}
        taken={taken}
        onEdit={(entry) => setEditing({ room, day, entry })}
        onQuick={(status) => quick(room, day, status)}
      />
    )
  }
  const roomHead = (room: Room) => (
    <RoomHead
      room={room}
      watching={watching.includes(room.id)}
      onWatch={() => toggleWatch(room)}
      onQr={canManage ? () => setQrFor(room) : undefined}
    />
  )

  const border = '1px solid var(--mantine-color-default-border)'
  const legend = (
    <Group gap={6}>
      {(['going', 'maybe', 'here'] as OnsiteStatus[]).map((s) => (
        <Badge
          key={s}
          size="sm"
          variant="light"
          color={ONSITE_COLOR[s]}
          style={{ textTransform: 'none' }}
        >
          {t(`booking.onsite.status.${s}`)}
        </Badge>
      ))}
      <Badge
        size="sm"
        variant="light"
        color="gray"
        leftSection={<IconKey size={11} />}
        style={{ textTransform: 'none' }}
      >
        {t('booking.onsite.key')}
      </Badge>
    </Group>
  )

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <Group gap={4} wrap="nowrap">
            <ActionIcon
              variant="default"
              size="lg"
              aria-label={t('booking.calendar.prev')}
              onClick={() => shift(-1)}
            >
              <IconChevronLeft size={16} />
            </ActionIcon>
            <Button variant="default" onClick={() => setAnchor(new Date())}>
              {t('booking.calendar.today')}
            </Button>
            <ActionIcon
              variant="default"
              size="lg"
              aria-label={t('booking.calendar.next')}
              onClick={() => shift(1)}
            >
              <IconChevronRight size={16} />
            </ActionIcon>
          </Group>
          <Text fw={600} truncate>
            {rangeLabel}
          </Text>
        </Group>
        <Box w={phone ? '100%' : undefined}>
          <SegmentedControl
            size={phone ? 'sm' : 'xs'}
            fullWidth={phone}
            value={view}
            onChange={(v) => pickView(v as 'week' | 'month')}
            data={[
              { value: 'week', label: t('booking.onsite.week') },
              { value: 'month', label: t('booking.onsite.month') },
            ]}
          />
        </Box>
      </Group>
      <Stack gap={6}>
        <Text size="sm" c="dimmed">
          {t('booking.onsite.intro')}
        </Text>
        {legend}
      </Stack>

      {month ? (
        <MonthGrid
          days={days}
          inMonth={anchor.getMonth()}
          today={today}
          picked={phone ? picked : undefined}
          compact={!!phone}
          locale={locale}
          rooms={rooms}
          entries={entries}
          onPick={(d) => {
            setAnchor(d)
            if (!phone) pickView('week')
          }}
        />
      ) : phone ? (
        <WeekStrip
          days={days}
          picked={picked}
          today={today}
          locale={locale}
          rooms={rooms}
          entries={entries}
          onPick={setAnchor}
        />
      ) : (
        <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
          <ScrollArea type="auto">
            <Box
              style={{
                display: 'grid',
                gridTemplateColumns: `180px repeat(7, minmax(120px, 1fr))`,
                minWidth: 1020,
              }}
            >
              <div
                style={{
                  borderBottom: border,
                  position: 'sticky',
                  left: 0,
                  zIndex: 1,
                  background: 'var(--mantine-color-body)',
                }}
              />
              {days.map((d) => {
                const day = isoDay(d)
                const s = summary(entries, day)
                return (
                  <Box
                    key={day}
                    py={6}
                    ta="center"
                    style={{
                      borderLeft: border,
                      borderBottom: border,
                      background: day === today ? 'var(--mantine-color-violet-light)' : undefined,
                    }}
                  >
                    <Text size="xs" c="dimmed" tt="uppercase">
                      {d.toLocaleDateString(locale, { weekday: 'short' })}
                    </Text>
                    <Text fw={day === today ? 700 : 500} c={day === today ? 'violet' : undefined}>
                      {d.getDate()}
                    </Text>
                    <Text size="xs" c="dimmed" h={18}>
                      {s.count ? t('booking.onsite.people', { count: s.count }) : ''}
                    </Text>
                  </Box>
                )
              })}
              {rooms.map((room, i) => (
                <Box key={room.id} style={{ display: 'contents' }}>
                  <Box
                    p="sm"
                    style={{
                      borderTop: i ? border : undefined,
                      position: 'sticky',
                      left: 0,
                      zIndex: 1,
                      background: 'var(--mantine-color-body)',
                    }}
                  >
                    {roomHead(room)}
                  </Box>
                  {days.map((d) => {
                    const day = isoDay(d)
                    return (
                      <Box
                        key={day}
                        p={6}
                        style={{
                          borderLeft: border,
                          borderTop: i ? border : undefined,
                          background:
                            day < today
                              ? 'var(--mantine-color-default-hover)'
                              : day === today
                                ? 'color-mix(in srgb, var(--mantine-color-violet-light) 45%, transparent)'
                                : undefined,
                        }}
                      >
                        {cell(room, d)}
                      </Box>
                    )
                  })}
                </Box>
              ))}
            </Box>
          </ScrollArea>
        </Paper>
      )}

      {phone && (
        <Stack gap="sm">
          <Text fw={600}>
            {anchor.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
          </Text>
          {rooms.map((room) => (
            <Paper key={room.id} withBorder radius="md" p="sm">
              {roomHead(room)}
              <Box mt="xs">{cell(room, anchor)}</Box>
            </Paper>
          ))}
        </Stack>
      )}

      <NextDays
        data={soon.data}
        loading={soon.isLoading}
        locale={locale}
        onEdit={(room, day, entry) => setEditing({ room, day, entry })}
        onQuick={quick}
        onPick={(day) => {
          setAnchor(new Date(`${day}T12:00`))
          if (!phone) pickView('week')
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }}
      />

      {qrFor && <QrModal room={qrFor} onClose={() => setQrFor(null)} />}
      {editing && (
        <OnsiteModal
          room={editing.room}
          day={editing.day}
          entry={editing.entry}
          isToday={editing.day === today}
          onClose={() => setEditing(null)}
          onSaved={refresh}
        />
      )}
    </Stack>
  )
}

/** The phone's week: a column per day, a row per room with how many come.
 * Tapping a day lists its rooms below. */
function WeekStrip({
  days,
  picked,
  today,
  locale,
  rooms,
  entries,
  onPick,
}: {
  days: Date[]
  picked: string
  today: string
  locale: string
  rooms: Room[]
  entries: OnsiteEntry[]
  onPick: (d: Date) => void
}) {
  const border = '1px solid var(--mantine-color-default-border)'
  const col = (day: string) => ({
    background:
      day === picked
        ? 'var(--mantine-color-violet-light)'
        : day < today
          ? 'var(--mantine-color-default-hover)'
          : undefined,
  })
  return (
    <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
      <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
        {days.map((d) => {
          const day = isoDay(d)
          return (
            <UnstyledButton
              key={day}
              onClick={() => onPick(d)}
              aria-pressed={day === picked}
              aria-label={d.toLocaleDateString(locale, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
              py={6}
              ta="center"
              style={{ ...col(day), borderBottom: border }}
            >
              <Text size="xs" c="dimmed" tt="uppercase">
                {d.toLocaleDateString(locale, { weekday: 'short' }).slice(0, 2)}
              </Text>
              <Text
                fw={day === today || day === picked ? 700 : 500}
                c={day === today ? 'violet' : undefined}
              >
                {d.getDate()}
              </Text>
            </UnstyledButton>
          )
        })}
        {rooms.map((room, i) => (
          <Box key={room.id} style={{ display: 'contents' }}>
            <Text
              size="xs"
              fw={600}
              c="dimmed"
              px={8}
              pt={6}
              truncate
              style={{ gridColumn: '1 / -1', borderTop: i ? border : undefined }}
            >
              {room.name}
            </Text>
            {days.map((d) => {
              const day = isoDay(d)
              const s = summary(entries, day, room.id)
              return (
                <UnstyledButton
                  key={day}
                  onClick={() => onPick(d)}
                  tabIndex={-1}
                  aria-hidden
                  h={34}
                  style={{
                    ...col(day),
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 2,
                  }}
                >
                  {s.count ? (
                    <>
                      <CountDot s={s} />
                      {s.key && <IconKey size={11} />}
                    </>
                  ) : (
                    <Text size="xs" c="dimmed">
                      ·
                    </Text>
                  )}
                </UnstyledButton>
              )
            })}
          </Box>
        ))}
      </Box>
    </Paper>
  )
}

/** A month: per day and room how many are coming, and the key. On a wide
 * screen a day opens its week; on the phone (compact) a day shows the total
 * and is picked. */
function MonthGrid({
  days,
  inMonth,
  today,
  picked,
  compact,
  locale,
  rooms,
  entries,
  onPick,
}: {
  days: Date[]
  inMonth: number
  today: string
  picked?: string
  compact: boolean
  locale: string
  rooms: Room[]
  entries: OnsiteEntry[]
  onPick: (d: Date) => void
}) {
  const { t } = useT()
  const border = '1px solid var(--mantine-color-default-border)'
  return (
    <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
      <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
        {days.slice(0, 7).map((d) => (
          <Text
            key={d.getDay()}
            size="xs"
            c="dimmed"
            tt="uppercase"
            ta="center"
            py={4}
            style={{ borderBottom: border }}
          >
            {d.toLocaleDateString(locale, { weekday: 'short' }).slice(0, compact ? 2 : undefined)}
          </Text>
        ))}
        {days.map((d, i) => {
          const day = isoDay(d)
          const all = summary(entries, day)
          return (
            <UnstyledButton
              key={day}
              onClick={() => onPick(d)}
              aria-pressed={picked ? day === picked : undefined}
              aria-label={d.toLocaleDateString(locale, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
              p={compact ? 4 : 6}
              style={{
                minHeight: compact ? 54 : 76,
                borderLeft: i % 7 ? border : undefined,
                borderTop: i >= 7 ? border : undefined,
                background:
                  day === picked
                    ? 'var(--mantine-color-violet-light)'
                    : day < today
                      ? 'var(--mantine-color-default-hover)'
                      : undefined,
                opacity: d.getMonth() === inMonth ? 1 : 0.45,
                outline:
                  !compact && all.mine ? '2px solid var(--mantine-color-violet-filled)' : undefined,
                outlineOffset: -2,
              }}
            >
              <Text
                size="sm"
                ta={compact ? 'center' : undefined}
                fw={day === today ? 700 : 500}
                c={day === today ? 'violet' : undefined}
              >
                {d.getDate()}
              </Text>
              {compact ? (
                all.count > 0 && (
                  <Group gap={2} justify="center" wrap="nowrap" mt={2}>
                    <CountDot s={all} size="xs" />
                    {all.key && <IconKey size={10} />}
                  </Group>
                )
              ) : (
                <Stack gap={2} mt={2}>
                  {rooms.map((room) => {
                    const s = summary(entries, day, room.id)
                    if (!s.count) return null
                    return (
                      <Group key={room.id} gap={4} wrap="nowrap">
                        <Badge
                          size="sm"
                          variant="light"
                          color={s.sure ? 'green' : 'yellow'}
                          style={{ textTransform: 'none', flexShrink: 0 }}
                          title={s.people.map((e) => e.memberName).join(', ')}
                        >
                          {t('booking.onsite.count', { count: s.count })}
                        </Badge>
                        <Text size="xs" truncate style={{ flex: 1, minWidth: 0 }}>
                          {room.name}
                        </Text>
                        {s.key && <IconKey size={12} aria-label={t('booking.onsite.key')} />}
                      </Group>
                    )
                  })}
                </Stack>
              )}
            </UnstyledButton>
          )
        })}
      </Box>
    </Paper>
  )
}

/** How far ahead the list under the calendar looks. */
const NEXT_DAYS = 14

/** Under the calendar: the next two weeks, a card per day with who comes to
 * which room. */
function NextDays({
  data,
  loading,
  locale,
  onEdit,
  onQuick,
  onPick,
}: {
  data?: OnsiteData
  loading: boolean
  locale: string
  onEdit: (room: Room, day: string, entry?: OnsiteEntry) => void
  onQuick: (room: Room, day: string, status: OnsiteStatus) => void
  onPick: (day: string) => void
}) {
  const { t } = useT()
  const today = data?.today ?? isoDay(new Date())
  const tomorrow = isoDay(addDays(new Date(`${today}T12:00`), 1))
  const groups = useMemo(() => {
    if (!data) return []
    const byDay = new Map<string, OnsiteEntry[]>()
    for (const e of data.entries) {
      if (e.day < today) continue
      byDay.set(e.day, [...(byDay.get(e.day) ?? []), e])
    }
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, list]) => ({
        day,
        rooms: data.rooms
          .map((room) => ({
            room,
            people: list
              .filter((e) => e.resourceId === room.id)
              .sort(
                (a, b) =>
                  Number(b.mine) - Number(a.mine) || (a.from ?? '').localeCompare(b.from ?? ''),
              ),
          }))
          .filter((r) => r.people.length),
      }))
  }, [data, today])

  return (
    <Stack gap="sm" mt="md">
      <Box>
        <Text fw={700} size="lg">
          {t('booking.onsite.next.title')}
        </Text>
        <Text size="sm" c="dimmed">
          {t('booking.onsite.next.hint')}
        </Text>
      </Box>
      {loading ? (
        <LoadingSpinner />
      ) : !groups.length ? (
        <Paper withBorder radius="md" p="md">
          <Text size="sm" c="dimmed">
            {t('booking.onsite.next.empty')}
          </Text>
        </Paper>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
          {groups.map(({ day, rooms }) => {
            const d = new Date(`${day}T12:00`)
            const total = rooms.reduce((n, r) => n + r.people.length, 0)
            return (
              <Paper key={day} withBorder radius="md" p="sm">
                <Group justify="space-between" wrap="nowrap" gap="xs" mb="xs">
                  <UnstyledButton onClick={() => onPick(day)} style={{ minWidth: 0 }}>
                    <Group gap={8} wrap="nowrap">
                      <Box
                        w={40}
                        ta="center"
                        py={2}
                        style={{
                          borderRadius: 8,
                          background:
                            day === today
                              ? 'var(--mantine-color-violet-filled)'
                              : 'var(--mantine-color-default-hover)',
                          color: day === today ? 'var(--mantine-color-white)' : undefined,
                          flexShrink: 0,
                        }}
                      >
                        <Text
                          size="xs"
                          tt="uppercase"
                          lh={1.2}
                          c={day === today ? 'inherit' : 'dimmed'}
                        >
                          {d.toLocaleDateString(locale, { weekday: 'short' }).slice(0, 2)}
                        </Text>
                        <Text fw={700} lh={1.2}>
                          {d.getDate()}
                        </Text>
                      </Box>
                      <Box style={{ minWidth: 0 }}>
                        <Text fw={600} truncate>
                          {day === today
                            ? t('booking.calendar.today')
                            : day === tomorrow
                              ? t('booking.onsite.next.tomorrow')
                              : d.toLocaleDateString(locale, { weekday: 'long' })}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {d.toLocaleDateString(locale, { day: 'numeric', month: 'long' })}
                        </Text>
                      </Box>
                    </Group>
                  </UnstyledButton>
                  <Badge
                    variant="light"
                    color="gray"
                    style={{ textTransform: 'none', flexShrink: 0 }}
                  >
                    {t('booking.onsite.people', { count: total })}
                  </Badge>
                </Group>
                <Stack gap="sm">
                  {rooms.map(({ room, people }) => {
                    const mine = people.find((e) => e.mine)
                    const key = people.some((e) => e.keyHolder)
                    return (
                      <Box key={room.id}>
                        <Group justify="space-between" gap={4} wrap="nowrap" mb={4}>
                          <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                            <IconMapPin size={14} style={{ flexShrink: 0 }} />
                            <Text size="sm" fw={600} truncate>
                              {room.name}
                            </Text>
                            {!key && (
                              <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                                · {t('booking.onsite.noKey')}
                              </Text>
                            )}
                          </Group>
                          {!mine && (
                            <Button
                              size="compact-xs"
                              variant="light"
                              onClick={() => onQuick(room, day, day === today ? 'here' : 'going')}
                            >
                              {day === today
                                ? t('booking.onsite.imHere')
                                : t('booking.onsite.meToo')}
                            </Button>
                          )}
                        </Group>
                        <Stack gap={4}>
                          {people.map((e) => (
                            <EntryLine
                              key={e.id}
                              e={e}
                              onEdit={e.mine ? () => onEdit(room, day, e) : undefined}
                            />
                          ))}
                        </Stack>
                      </Box>
                    )
                  })}
                </Stack>
              </Paper>
            )
          })}
        </SimpleGrid>
      )}
    </Stack>
  )
}

/** One person's entry: name, key, time and comment, in the status colour. */
function EntryLine({ e, onEdit }: { e: OnsiteEntry; onEdit?: () => void }) {
  const { t } = useT()
  return (
    <UnstyledButton
      onClick={onEdit}
      style={{
        cursor: onEdit ? 'pointer' : 'default',
        borderRadius: 6,
        padding: '2px 6px',
        borderLeft: `3px solid var(--mantine-color-${ONSITE_COLOR[e.status]}-filled)`,
        background: `var(--mantine-color-${ONSITE_COLOR[e.status]}-light)`,
        opacity: e.status === 'maybe' ? 0.85 : 1,
      }}
      title={e.comment ?? undefined}
    >
      <Group gap={4} wrap="nowrap">
        <Text size="xs" fw={e.mine ? 700 : 500} truncate style={{ flex: 1 }}>
          {e.mine ? t('booking.onsite.me') : e.memberName}
        </Text>
        {e.keyHolder && <IconKey size={12} aria-label={t('booking.onsite.key')} />}
      </Group>
      {(e.from || e.to || e.comment) && (
        <Text size="xs" c="dimmed" lh={1.3} truncate>
          {[timeText(e, t), e.comment].filter(Boolean).join(' · ')}
        </Text>
      )}
    </UnstyledButton>
  )
}

function RoomHead({
  room,
  watching,
  onWatch,
  onQr,
}: {
  room: Room
  watching: boolean
  onWatch: () => void
  onQr?: () => void
}) {
  const { t } = useT()
  return (
    <Group justify="space-between" wrap="nowrap" gap={4}>
      <Box style={{ minWidth: 0 }}>
        <Text fw={600} truncate>
          {room.name}
        </Text>
        {room.location && (
          <Text size="xs" c="dimmed" truncate>
            {room.location}
          </Text>
        )}
      </Box>
      <Group gap={2} wrap="nowrap">
        {onQr && (
          <Tooltip label={t('booking.onsite.qr')}>
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label={t('booking.onsite.qr')}
              onClick={onQr}
            >
              <IconQrcode size={16} />
            </ActionIcon>
          </Tooltip>
        )}
        <Tooltip label={watching ? t('booking.onsite.unwatch') : t('booking.onsite.watch')}>
          <ActionIcon
            variant={watching ? 'light' : 'subtle'}
            color={watching ? 'violet' : 'gray'}
            aria-label={watching ? t('booking.onsite.unwatch') : t('booking.onsite.watch')}
            aria-pressed={watching}
            onClick={onWatch}
          >
            {watching ? <IconBell size={16} /> : <IconBellOff size={16} />}
          </ActionIcon>
        </Tooltip>
      </Group>
    </Group>
  )
}

function Cell({
  day,
  past,
  isToday,
  people,
  taken,
  onEdit,
  onQuick,
}: {
  room: Room
  day: string
  past: boolean
  isToday: boolean
  people: OnsiteEntry[]
  taken: OnsiteData['busy']
  onEdit: (entry?: OnsiteEntry) => void
  onQuick: (status: OnsiteStatus) => void
}) {
  const { t } = useT()
  const mine = people.find((e) => e.mine)
  const key = people.some((e) => e.keyHolder)
  return (
    <Stack gap={4} data-day={day}>
      {taken.map((b, i) => (
        <Text key={i} size="xs" c="orange" fw={500} lh={1.3} title={b.title ?? undefined}>
          {t('booking.onsite.busy', {
            from: b.startsAt.slice(0, 10) < day ? '00:00' : hhmm(b.startsAt),
            to: b.endsAt.slice(0, 10) > day ? '24:00' : hhmm(b.endsAt),
          })}
          {b.title ? ` · ${b.title}` : ''}
        </Text>
      ))}
      {people.map((e) => (
        <EntryLine key={e.id} e={e} onEdit={e.mine && !past ? () => onEdit(e) : undefined} />
      ))}
      {!past && !mine && (
        <Group gap={4} wrap="nowrap">
          {people.length > 0 ? (
            <Button
              size="compact-xs"
              variant="light"
              onClick={() => onQuick(isToday ? 'here' : 'going')}
            >
              {isToday ? t('booking.onsite.imHere') : t('booking.onsite.meToo')}
            </Button>
          ) : null}
          <Tooltip label={t('booking.onsite.add')}>
            <ActionIcon
              size="sm"
              variant="subtle"
              aria-label={t('booking.onsite.add')}
              onClick={() => onEdit()}
            >
              <IconPlus size={14} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )}
      {!past && people.length > 0 && !key && (
        <Text size="xs" c="dimmed">
          {t('booking.onsite.noKey')}
        </Text>
      )}
    </Stack>
  )
}

/** The caller's own entry for a room and day. */
function OnsiteModal({
  room,
  day,
  entry,
  isToday,
  onClose,
  onSaved,
}: {
  room: Room
  day: string
  entry?: OnsiteEntry
  isToday: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const { t, i18n } = useT()
  const { busy, run } = useAction()
  const [status, setStatus] = useState<OnsiteStatus>(entry?.status ?? (isToday ? 'here' : 'going'))
  const [from, setFrom] = useState(entry?.from ?? '')
  const [to, setTo] = useState(entry?.to ?? '')
  const [keyHolder, setKeyHolder] = useState(entry?.keyHolder ?? false)
  const [comment, setComment] = useState(entry?.comment ?? '')
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'
  const label = new Date(`${day}T12:00`).toLocaleDateString(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
  const bad = !!from && !!to && to <= from

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (bad) return
    const ok = await run(
      () =>
        setOnsite({
          resourceId: room.id,
          day,
          status,
          from: from || null,
          to: to || null,
          keyHolder,
          comment: comment || null,
        }),
      t('booking.onsite.saved'),
    )
    if (ok) {
      onSaved()
      onClose()
    }
  }
  const remove = async () => {
    if (entry && (await run(() => deleteOnsite(entry.id), t('booking.onsite.removed')))) {
      onSaved()
      onClose()
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={`${room.name} · ${label}`}
      footer={
        <>
          {entry && (
            <Button variant="subtle" color="red" mr="auto" onClick={remove} loading={busy}>
              {t('booking.onsite.remove')}
            </Button>
          )}
          <Button variant="default" onClick={onClose}>
            {t('booking.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={bad}>
            {t('booking.onsite.save')}
          </Button>
        </>
      }
    >
      <SegmentedControl
        fullWidth
        value={status}
        onChange={(v) => setStatus(v as OnsiteStatus)}
        data={(['going', 'maybe', ...(isToday ? ['here'] : [])] as OnsiteStatus[]).map((s) => ({
          value: s,
          label: t(`booking.onsite.status.${s}`),
        }))}
      />
      <Field label={t('booking.onsite.time')} hint={t('booking.onsite.timeHint')}>
        <Group gap="xs" grow wrap="nowrap">
          <TextInput
            type="time"
            aria-label={t('booking.onsite.timeFrom')}
            value={from}
            onChange={(e) => setFrom(e.currentTarget.value)}
          />
          <TextInput
            type="time"
            aria-label={t('booking.onsite.timeTo')}
            value={to}
            onChange={(e) => setTo(e.currentTarget.value)}
          />
        </Group>
      </Field>
      {bad && (
        <Text size="sm" c="red">
          {t('booking.endBeforeStart')}
        </Text>
      )}
      <Field label={t('booking.onsite.comment')}>
        <TextInput
          value={comment}
          maxLength={300}
          onChange={(e) => setComment(e.currentTarget.value)}
          placeholder={t('booking.onsite.commentExample')}
        />
      </Field>
      <Checkbox
        checked={keyHolder}
        onChange={(e) => setKeyHolder(e.currentTarget.checked)}
        label={t('booking.onsite.keyHolder')}
        description={t('booking.onsite.keyHolderHint')}
      />
      <Text size="xs" c="dimmed">
        {t('booking.onsite.reminderNote')}
      </Text>
    </Modal>
  )
}

/** The QR code fills its box (qrcode's SVG has a fixed size in mm). */
const fitSvg = (svg: string) =>
  svg.replace(/<svg([^>]*?)\swidth="[^"]*"\s+height="[^"]*"/, '<svg$1 width="100%" height="100%"')

/** A room's QR code to print and hang at the door: scanning it checks the
 * member in for today. */
function QrModal({ room, onClose }: { room: Room; onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const qr = useQuery({
    queryKey: ['booking', 'onsite-qr', room.id],
    queryFn: () => getOnsiteQr(room.id),
  })
  const renew = () =>
    run(() => renewOnsiteQr(room.id), t('booking.onsite.qrRenewed')).then((ok) => {
      if (ok) qc.invalidateQueries({ queryKey: ['booking', 'onsite-qr', room.id] })
    })
  const print = () => {
    if (!qr.data) return
    const w = window.open('', '_blank', 'width=700,height=900')
    if (!w) return
    const esc = (s: string) =>
      s.replace(
        /[&<>"]/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string,
      )
    w.document.write(
      `<!doctype html><html><head><meta charset="utf-8"><title>${esc(room.name)}</title>` +
        `<style>body{font-family:system-ui,sans-serif;text-align:center;padding:40px}h1{font-size:40px;margin:0 0 8px}` +
        `p{font-size:20px;color:#444}svg{width:420px;height:420px}</style></head><body>` +
        `<h1>${esc(room.name)}</h1><p>${esc(t('booking.onsite.qrPoster'))}</p>${fitSvg(qr.data.svg)}` +
        `<p style="font-size:12px;color:#888">${esc(qr.data.url)}</p></body></html>`,
    )
    w.document.close()
    w.focus()
    w.print()
  }
  return (
    <Modal
      open
      onClose={onClose}
      title={t('booking.onsite.qrTitle', { room: room.name })}
      footer={
        <>
          <Button
            variant="subtle"
            color="red"
            mr="auto"
            leftSection={<IconRefresh size={16} />}
            loading={busy}
            onClick={renew}
          >
            {t('booking.onsite.qrRenew')}
          </Button>
          <Button variant="default" onClick={onClose}>
            {t('booking.onsite.close')}
          </Button>
          <Button leftSection={<IconPrinter size={16} />} disabled={!qr.data} onClick={print}>
            {t('booking.onsite.qrPrint')}
          </Button>
        </>
      }
    >
      {qr.error ? (
        <ErrorBanner message={errorText(qr.error)} onRetry={() => qr.refetch()} />
      ) : !qr.data ? (
        <LoadingSpinner />
      ) : (
        <Stack align="center" gap="xs">
          <Box
            w={240}
            h={240}
            style={{ background: '#fff', borderRadius: 8 }}
            dangerouslySetInnerHTML={{ __html: fitSvg(qr.data.svg) }}
          />
          <Text size="sm" ta="center">
            {t('booking.onsite.qrHint')}
          </Text>
          <Text size="xs" c="dimmed" ta="center" style={{ wordBreak: 'break-all' }}>
            {qr.data.url}
          </Text>
        </Stack>
      )}
    </Modal>
  )
}
