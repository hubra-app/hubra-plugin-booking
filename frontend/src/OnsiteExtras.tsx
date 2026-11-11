import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Badge,
  Box,
  Button,
  CopyButton,
  Group,
  Paper,
  Progress,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core'
import { IconDoorExit, IconKey, IconRefresh } from '@tabler/icons-react'
import { ErrorBanner, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import {
  errorText,
  getOnsiteFeed,
  getOnsiteStats,
  leaveOnsite,
  renewOnsiteFeed,
  type OnsiteData,
  type OnsiteEntry,
} from './api'
import { useAction } from './common'

/** "Jetzt da": who checked in today (Bin da) and hasn't left, per room. The
 * caller can check out. An entry with an end time drops off after it. */
export function NowHere({ data, onChanged }: { data?: OnsiteData; onChanged: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  if (!data) return null
  const now = new Date()
  const clock = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const here = data.entries.filter(
    (e) => e.day === data.today && e.status === 'here' && !e.leftAt && (!e.to || e.to > clock),
  )
  if (!here.length) return null
  const rooms = data.rooms.filter((r) => here.some((e) => e.resourceId === r.id))
  return (
    <Paper
      withBorder
      radius="md"
      p="sm"
      style={{ borderColor: 'var(--mantine-color-green-filled)' }}
    >
      <Group gap={8} mb={6}>
        <Box
          w={10}
          h={10}
          style={{ borderRadius: 99, background: 'var(--mantine-color-green-filled)' }}
        />
        <Text fw={700}>{t('booking.onsite.now.title')}</Text>
      </Group>
      <Stack gap={6}>
        {rooms.map((room) => {
          const people = here.filter((e) => e.resourceId === room.id)
          const mine = people.find((e) => e.mine)
          return (
            <Group key={room.id} justify="space-between" gap="xs" wrap="wrap">
              <Group gap={6} wrap="wrap" style={{ minWidth: 0 }}>
                <Text size="sm" fw={600}>
                  {room.name}
                </Text>
                {people.map((e) => (
                  <Badge
                    key={e.id}
                    variant="light"
                    color={e.mine ? 'violet' : 'green'}
                    style={{ textTransform: 'none' }}
                    rightSection={e.keyHolder ? <IconKey size={11} /> : undefined}
                  >
                    {e.mine ? t('booking.onsite.me') : e.memberName}
                  </Badge>
                ))}
              </Group>
              {mine && (
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="gray"
                  leftSection={<IconDoorExit size={14} />}
                  loading={busy}
                  onClick={() =>
                    run(() => leaveOnsite(mine.id), t('booking.onsite.now.left')).then((ok) => {
                      if (ok) onChanged()
                    })
                  }
                >
                  {t('booking.onsite.now.leave')}
                </Button>
              )}
            </Group>
          )
        })}
      </Stack>
    </Paper>
  )
}

/** The caller's calendar feed (own days and watched rooms) to subscribe to. */
export function FeedModal({ onClose }: { onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const feed = useQuery({ queryKey: ['booking', 'onsite-feed'], queryFn: getOnsiteFeed })
  const renew = () =>
    run(() => renewOnsiteFeed(), t('booking.onsite.feed.renewed')).then((ok) => {
      if (ok) qc.invalidateQueries({ queryKey: ['booking', 'onsite-feed'] })
    })
  const url = feed.data?.url ?? ''
  return (
    <Modal
      open
      onClose={onClose}
      title={t('booking.onsite.feed.title')}
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
            {t('booking.onsite.feed.renew')}
          </Button>
          <Button variant="default" onClick={onClose}>
            {t('booking.onsite.close')}
          </Button>
        </>
      }
    >
      <Text size="sm">{t('booking.onsite.feed.hint')}</Text>
      {feed.error ? (
        <ErrorBanner message={errorText(feed.error)} onRetry={() => feed.refetch()} />
      ) : !feed.data ? (
        <LoadingSpinner />
      ) : (
        <Group gap="xs" wrap="nowrap" align="flex-end">
          <TextInput
            readOnly
            value={url}
            aria-label={t('booking.onsite.feed.title')}
            style={{ flex: 1 }}
            onFocus={(e) => e.currentTarget.select()}
          />
          <CopyButton value={url}>
            {({ copied, copy }) => (
              <Button variant={copied ? 'light' : 'filled'} onClick={copy}>
                {copied ? t('booking.onsite.feed.copied') : t('booking.onsite.feed.copy')}
              </Button>
            )}
          </CopyButton>
        </Group>
      )}
      <Text size="xs" c="dimmed">
        {t('booking.onsite.feed.private')}
      </Text>
    </Modal>
  )
}

/** For the board: how much the rooms are used, per month and weekday. */
export function StatsModal({ locale, onClose }: { locale: string; onClose: () => void }) {
  const { t } = useT()
  const [months, setMonths] = useState('6')
  const stats = useQuery({
    queryKey: ['booking', 'onsite-stats', months],
    queryFn: () => getOnsiteStats(Number(months)),
  })
  const s = stats.data
  const top = s ? Math.max(1, ...s.weekdays) : 1
  // Monday first, like the calendar.
  const weekday = (i: number) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: 'short' })
  const monthLabel = (m: string) =>
    new Date(`${m}-15T12:00`).toLocaleDateString(locale, { month: 'short' })
  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={t('booking.onsite.stats.title')}
      footer={
        <Button variant="default" onClick={onClose}>
          {t('booking.onsite.close')}
        </Button>
      }
    >
      <SegmentedControl
        value={months}
        onChange={setMonths}
        data={['3', '6', '12'].map((m) => ({
          value: m,
          label: t('booking.onsite.stats.months', { count: Number(m) }),
        }))}
      />
      {stats.error ? (
        <ErrorBanner message={errorText(stats.error)} onRetry={() => stats.refetch()} />
      ) : !s ? (
        <LoadingSpinner />
      ) : (
        <Stack gap="md">
          <Group gap="xl">
            <Box>
              <Text size="xl" fw={700}>
                {s.total.visits}
              </Text>
              <Text size="xs" c="dimmed">
                {t('booking.onsite.stats.visits')}
              </Text>
            </Box>
            <Box>
              <Text size="xl" fw={700}>
                {s.total.people}
              </Text>
              <Text size="xs" c="dimmed">
                {t('booking.onsite.stats.people')}
              </Text>
            </Box>
          </Group>
          <Box style={{ overflowX: 'auto' }}>
            <Table striped withTableBorder fz="sm" horizontalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('booking.onsite.stats.room')}</Table.Th>
                  {s.months.map((m) => (
                    <Table.Th key={m.month} ta="right">
                      {monthLabel(m.month)}
                    </Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {s.rooms.map((room) => (
                  <Table.Tr key={room.id}>
                    <Table.Td fw={600}>{room.name}</Table.Td>
                    {s.months.map((m) => {
                      const c = m.rooms.find((r) => r.resourceId === room.id)
                      return (
                        <Table.Td
                          key={m.month}
                          ta="right"
                          title={
                            c
                              ? `${t('booking.onsite.stats.days')}: ${c.days} · ${t('booking.onsite.stats.people')}: ${c.people}`
                              : undefined
                          }
                        >
                          {c?.visits || '–'}
                          {c?.days ? (
                            <Text span size="xs" c="dimmed">
                              {' '}
                              / {c.days}
                            </Text>
                          ) : null}
                        </Table.Td>
                      )
                    })}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Box>
          <Text size="xs" c="dimmed">
            {t('booking.onsite.stats.hint')}
          </Text>
          <Box>
            <Text fw={600} size="sm" mb={6}>
              {t('booking.onsite.stats.weekdays')}
            </Text>
            <Stack gap={4}>
              {s.weekdays.map((n, i) => (
                <Group key={i} gap="xs" wrap="nowrap">
                  <Text size="xs" w={28} c="dimmed" tt="uppercase">
                    {weekday(i)}
                  </Text>
                  <Progress value={(n / top) * 100} style={{ flex: 1 }} color="violet" />
                  <Text size="xs" w={28} ta="right">
                    {n}
                  </Text>
                </Group>
              ))}
            </Stack>
          </Box>
        </Stack>
      )}
    </Modal>
  )
}

/** Who joins whose plan in a room on a day ("Mitmachen"). */
export function joinInfo(e: OnsiteEntry, people: OnsiteEntry[]) {
  return {
    joiners: people.filter((p) => p.joinsId === e.id).length,
    host: e.joinsId ? (people.find((p) => p.id === e.joinsId) ?? null) : null,
    joinedByMe: people.some((p) => p.mine && p.joinsId === e.id),
  }
}
