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
  IconPlus,
} from '@tabler/icons-react'
import { EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import {
  QK,
  addDays,
  deleteOnsite,
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

/** Vor Ort: who plans to be in which room on which day. A week of days by
 * rooms (a day on the phone); a cell shows the people, the key, and when the
 * room is booked. */
export function OnsiteTab() {
  const { t, i18n } = useT()
  const qc = useQueryClient()
  const phone = useMediaQuery('(max-width: 48em)')
  const { run } = useAction()
  const [anchor, setAnchor] = useState(() => {
    const asked = new URLSearchParams(window.location.search).get('day')
    return asked ? new Date(`${asked}T12:00`) : new Date()
  })
  const [editing, setEditing] = useState<{ room: Room; day: string; entry?: OnsiteEntry } | null>(
    null,
  )
  const [view, setView] = useState<'week' | 'month'>(() => {
    try {
      return localStorage.getItem('booking.onsiteView') === 'month' ? 'month' : 'week'
    } catch {
      return 'week'
    }
  })
  const pickView = (v: 'week' | 'month') => {
    setView(v)
    try {
      localStorage.setItem('booking.onsiteView', v)
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
    if (phone) return [new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate())]
    const first = weekStart(anchor)
    return Array.from({ length: 7 }, (_, i) => addDays(first, i))
  }, [anchor, phone, month])
  const from = isoDay(days[0])
  const to = isoDay(addDays(days[days.length - 1], 1))
  const data = useQuery({ queryKey: QK.onsite(from, to), queryFn: () => listOnsite(from, to) })
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
      month
        ? new Date(anchor.getFullYear(), anchor.getMonth() + n, 1)
        : addDays(anchor, n * (phone ? 1 : 7)),
    )
  const rangeLabel = month
    ? anchor.toLocaleDateString(locale, { month: 'long', year: 'numeric' })
    : phone
      ? days[0].toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
      : `${days[0].toLocaleDateString(locale, { day: 'numeric', month: 'short' })} – ${days[6].toLocaleDateString(
          locale,
          {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
          },
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

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm" wrap="wrap">
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
          <Text fw={600}>{rangeLabel}</Text>
        </Group>
        <SegmentedControl
          size="xs"
          value={view}
          onChange={(v) => pickView(v as 'week' | 'month')}
          data={[
            { value: 'week', label: t('booking.onsite.week') },
            { value: 'month', label: t('booking.onsite.month') },
          ]}
        />
        <Group gap="xs">
          {(['going', 'maybe', 'here'] as OnsiteStatus[]).map((s) => (
            <Badge
              key={s}
              variant="light"
              color={ONSITE_COLOR[s]}
              style={{ textTransform: 'none' }}
            >
              {t(`booking.onsite.status.${s}`)}
            </Badge>
          ))}
          <Badge
            variant="light"
            color="gray"
            leftSection={<IconKey size={12} />}
            style={{ textTransform: 'none' }}
          >
            {t('booking.onsite.key')}
          </Badge>
        </Group>
      </Group>
      <Text size="sm" c="dimmed">
        {t('booking.onsite.intro')}
      </Text>

      {month ? (
        <MonthGrid
          days={days}
          inMonth={anchor.getMonth()}
          today={today}
          locale={locale}
          rooms={rooms}
          entries={entries}
          onPick={(d) => {
            setAnchor(d)
            pickView('week')
          }}
        />
      ) : phone ? (
        <Stack gap="sm">
          {rooms.map((room) => (
            <Paper key={room.id} withBorder radius="md" p="sm">
              <RoomHead
                room={room}
                watching={watching.includes(room.id)}
                onWatch={() => toggleWatch(room)}
              />
              <Box mt="xs">{cell(room, days[0])}</Box>
            </Paper>
          ))}
        </Stack>
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
              <div style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }} />
              {days.map((d) => {
                const day = isoDay(d)
                return (
                  <Box
                    key={day}
                    py={6}
                    ta="center"
                    style={{
                      borderLeft: '1px solid var(--mantine-color-default-border)',
                      borderBottom: '1px solid var(--mantine-color-default-border)',
                    }}
                  >
                    <Text size="xs" c="dimmed" tt="uppercase">
                      {d.toLocaleDateString(locale, { weekday: 'short' })}
                    </Text>
                    <Text fw={day === today ? 700 : 500} c={day === today ? 'violet' : undefined}>
                      {d.getDate()}
                    </Text>
                  </Box>
                )
              })}
              {rooms.map((room, i) => (
                <Box key={room.id} style={{ display: 'contents' }}>
                  <Box
                    p="sm"
                    style={{
                      borderTop: i ? '1px solid var(--mantine-color-default-border)' : undefined,
                    }}
                  >
                    <RoomHead
                      room={room}
                      watching={watching.includes(room.id)}
                      onWatch={() => toggleWatch(room)}
                    />
                  </Box>
                  {days.map((d) => (
                    <Box
                      key={isoDay(d)}
                      p={6}
                      style={{
                        borderLeft: '1px solid var(--mantine-color-default-border)',
                        borderTop: i ? '1px solid var(--mantine-color-default-border)' : undefined,
                        background:
                          isoDay(d) < today ? 'var(--mantine-color-default-hover)' : undefined,
                      }}
                    >
                      {cell(room, d)}
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          </ScrollArea>
        </Paper>
      )}
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

/** A month: per day and room how many are coming, and the key. A day opens
 * its week. */
function MonthGrid({
  days,
  inMonth,
  today,
  locale,
  rooms,
  entries,
  onPick,
}: {
  days: Date[]
  inMonth: number
  today: string
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
            {d.toLocaleDateString(locale, { weekday: 'short' })}
          </Text>
        ))}
        {days.map((d, i) => {
          const day = isoDay(d)
          const here = entries.filter((e) => e.day === day)
          const mine = here.some((e) => e.mine)
          return (
            <UnstyledButton
              key={day}
              onClick={() => onPick(d)}
              aria-label={d.toLocaleDateString(locale, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
              p={6}
              style={{
                minHeight: 76,
                borderLeft: i % 7 ? border : undefined,
                borderTop: i >= 7 ? border : undefined,
                background: day < today ? 'var(--mantine-color-default-hover)' : undefined,
                opacity: d.getMonth() === inMonth ? 1 : 0.45,
                outline: mine ? '2px solid var(--mantine-color-violet-filled)' : undefined,
                outlineOffset: -2,
              }}
            >
              <Text
                size="sm"
                fw={day === today ? 700 : 500}
                c={day === today ? 'violet' : undefined}
              >
                {d.getDate()}
              </Text>
              <Stack gap={2} mt={2}>
                {rooms.map((room) => {
                  const people = here.filter((e) => e.resourceId === room.id)
                  if (!people.length) return null
                  const sure = people.filter((e) => e.status !== 'maybe').length
                  return (
                    <Group key={room.id} gap={4} wrap="nowrap">
                      <Badge
                        size="sm"
                        variant="light"
                        color={sure ? 'green' : 'yellow'}
                        style={{ textTransform: 'none', flexShrink: 0 }}
                        title={people.map((e) => e.memberName).join(', ')}
                      >
                        {t('booking.onsite.count', { count: people.length })}
                      </Badge>
                      <Text size="xs" truncate style={{ flex: 1, minWidth: 0 }}>
                        {room.name}
                      </Text>
                      {people.some((e) => e.keyHolder) && (
                        <IconKey size={12} aria-label={t('booking.onsite.key')} />
                      )}
                    </Group>
                  )
                })}
              </Stack>
            </UnstyledButton>
          )
        })}
      </Box>
    </Paper>
  )
}

function RoomHead({
  room,
  watching,
  onWatch,
}: {
  room: Room
  watching: boolean
  onWatch: () => void
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
        <UnstyledButton
          key={e.id}
          onClick={() => (e.mine && !past ? onEdit(e) : undefined)}
          style={{
            cursor: e.mine && !past ? 'pointer' : 'default',
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
