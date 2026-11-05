import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge, Group, Paper, Stack, Text } from '@mantine/core'
import { IconCalendarCheck, IconChecklist } from '@tabler/icons-react'
import { EmptyState, ErrorBanner, LoadingSpinner, useT } from '@hubra/plugin-sdk'
import { QK, errorText, listMine, listPending, parseLocal, type Booking, type Options } from './api'
import { BookingDetail, STATUS_COLOR, when } from './BookingModal'
import { chf } from './common'

function Row({ b, showWho, onOpen }: { b: Booking; showWho: boolean; onOpen: () => void }) {
  const { t } = useT()
  const past = parseLocal(b.endsAt) < new Date()
  return (
    <Paper withBorder p="sm" radius="md" style={{ cursor: 'pointer', opacity: past || b.status === 'cancelled' || b.status === 'rejected' ? 0.65 : 1 }} onClick={onOpen}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div style={{ minWidth: 0 }}>
          <Text fw={600} truncate>
            {b.resourceName}
            {b.title ? ` · ${b.title}` : ''}
          </Text>
          <Text size="sm" c="dimmed">
            {when(b)}
            {showWho && b.memberName ? ` · ${b.memberName}` : ''}
            {b.fee ? ` · ${chf(b.fee)}` : ''}
          </Text>
        </div>
        <Badge variant="light" color={STATUS_COLOR[b.status]} style={{ textTransform: 'none', flexShrink: 0 }}>
          {t(`booking.status.${b.status}`)}
        </Badge>
      </Group>
    </Paper>
  )
}

/** The caller's bookings: upcoming first, then the last 30 days. */
export function MineTab({ options }: { options: Options | undefined }) {
  const { t } = useT()
  const mine = useQuery({ queryKey: QK.mine, queryFn: listMine })
  const [open, setOpen] = useState<Booking | null>(null)
  if (mine.error) return <ErrorBanner message={errorText(mine.error)} onRetry={() => mine.refetch()} />
  if (mine.isLoading) return <LoadingSpinner />
  const now = new Date()
  const rows = mine.data ?? []
  const upcoming = rows.filter((b) => parseLocal(b.endsAt) >= now)
  const past = rows.filter((b) => parseLocal(b.endsAt) < now).reverse()
  if (!rows.length) return <EmptyState icon={<IconCalendarCheck size={28} />} title={t('booking.mine.none')} description={t('booking.mine.noneHint')} />
  return (
    <Stack gap="xs">
      {upcoming.map((b) => (
        <Row key={b.id} b={b} showWho={false} onOpen={() => setOpen(b)} />
      ))}
      {past.length > 0 && (
        <Text size="sm" c="dimmed" mt="sm">
          {t('booking.mine.past')}
        </Text>
      )}
      {past.map((b) => (
        <Row key={b.id} b={b} showWho={false} onOpen={() => setOpen(b)} />
      ))}
      {open && <BookingDetail booking={open} options={options} onClose={() => setOpen(null)} />}
    </Stack>
  )
}

/** Requests waiting for approval. */
export function RequestsTab({ options }: { options: Options | undefined }) {
  const { t } = useT()
  const pending = useQuery({ queryKey: QK.pending, queryFn: listPending })
  const [open, setOpen] = useState<Booking | null>(null)
  if (pending.error) return <ErrorBanner message={errorText(pending.error)} onRetry={() => pending.refetch()} />
  if (pending.isLoading) return <LoadingSpinner />
  if (!pending.data?.length) return <EmptyState icon={<IconChecklist size={28} />} title={t('booking.requests.none')} />
  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">
        {t('booking.requests.hint')}
      </Text>
      {pending.data.map((b) => (
        <Row key={b.id} b={b} showWho onOpen={() => setOpen(b)} />
      ))}
      {open && <BookingDetail booking={open} options={options} onClose={() => setOpen(null)} />}
    </Stack>
  )
}
