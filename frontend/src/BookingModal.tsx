import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Badge, Button, Checkbox, Group, NumberInput, Select, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { Field, MemberPicker, Modal, useT } from '@hubra/plugin-sdk'
import {
  QK,
  cancelBooking,
  createBooking,
  decideBooking,
  feeFor,
  formatDay,
  hhmm,
  parseLocal,
  type Booking,
  type Options,
  type Resource,
  type Status,
} from './api'
import { chf, useAction } from './common'

export const STATUS_COLOR: Record<Status, string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  cancelled: 'gray',
}

export function when(b: Booking) {
  const sameDay = b.startsAt.slice(0, 10) === b.endsAt.slice(0, 10)
  return sameDay
    ? `${formatDay(b.startsAt)} · ${hhmm(b.startsAt)}–${hhmm(b.endsAt)}`
    : `${formatDay(b.startsAt)} ${hhmm(b.startsAt)} – ${formatDay(b.endsAt)} ${hhmm(b.endsAt)}`
}

/** Book a slot. Approvers can book for someone else and repeat weekly. */
export function BookingModal({
  options,
  resources,
  resourceId,
  start,
  end,
  onClose,
}: {
  options: Options | undefined
  resources: Resource[]
  resourceId: number | null
  start: string
  end: string
  onClose: () => void
}) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const manager = !!options?.can.bookings
  const [rid, setRid] = useState<number | null>(resourceId ?? resources[0]?.id ?? null)
  const [startDay, setStartDay] = useState(start.slice(0, 10))
  const [startTime, setStartTime] = useState(start.slice(11, 16))
  const [endDay, setEndDay] = useState(end.slice(0, 10))
  const [endTime, setEndTime] = useState(end.slice(11, 16))
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [memberId, setMemberId] = useState<string | null>(options ? String(options.memberId) : null)
  const [weeks, setWeeks] = useState<number | string>(0)
  const resource = resources.find((r) => r.id === rid)
  const startsAt = `${startDay}T${startTime}`
  const endsAt = `${endDay}T${endTime}`
  const valid = !!rid && startDay && startTime && endDay && endTime && endsAt > startsAt
  const fee = feeFor(resource, startsAt, endsAt)
  const pending = resource?.needsApproval && !manager

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!valid) return
    const ok = await run(
      () =>
        createBooking({
          resourceId: rid,
          startsAt,
          endsAt,
          title: title || null,
          note: note || null,
          ...(manager ? { memberId: memberId ? Number(memberId) : undefined, repeatWeeks: Number(weeks) || 0 } : {}),
        }),
      pending ? t('booking.requested') : t('booking.booked'),
    )
    if (ok) {
      qc.invalidateQueries({ queryKey: QK.all })
      onClose()
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('booking.new')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('booking.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!valid}>
            {pending ? t('booking.request') : t('booking.book')}
          </Button>
        </>
      }
    >
      <Field label={t('booking.resource')}>
        <Select
          aria-label={t('booking.resource')}
          data={resources.map((r) => ({ value: String(r.id), label: r.name }))}
          value={rid ? String(rid) : null}
          onChange={(v) => setRid(v ? Number(v) : null)}
          allowDeselect={false}
        />
      </Field>
      <Stack gap="sm">
        <Field label={t('booking.from')}>
          <Group gap="xs" grow wrap="nowrap">
            <TextInput
              type="date"
              aria-label={t('booking.fromDay')}
              value={startDay}
              onChange={(e) => {
                const v = e.currentTarget.value
                if (endDay === startDay || endDay < v) setEndDay(v)
                setStartDay(v)
              }}
            />
            <TextInput type="time" aria-label={t('booking.fromTime')} value={startTime} onChange={(e) => setStartTime(e.currentTarget.value)} />
          </Group>
        </Field>
        <Field label={t('booking.to')}>
          <Group gap="xs" grow wrap="nowrap">
            <TextInput type="date" aria-label={t('booking.toDay')} value={endDay} min={startDay} onChange={(e) => setEndDay(e.currentTarget.value)} />
            <TextInput type="time" aria-label={t('booking.toTime')} value={endTime} onChange={(e) => setEndTime(e.currentTarget.value)} />
          </Group>
        </Field>
      </Stack>
      {startDay && endDay && endsAt <= startsAt && (
        <Text size="sm" c="red">
          {t('booking.endBeforeStart')}
        </Text>
      )}
      <Field label={t('booking.titleField')} hint={t('booking.titleHint')}>
        <TextInput value={title} onChange={(e) => setTitle(e.currentTarget.value)} placeholder={t('booking.titleExample')} />
      </Field>
      <Field label={t('booking.note')}>
        <Textarea value={note} onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} />
      </Field>
      {manager && (
        <Group grow align="flex-start">
          <Field label={t('booking.for')}>
            <MemberPicker value={memberId} onChange={(id) => setMemberId(id)} />
          </Field>
          <Field label={t('booking.repeat')} hint={t('booking.repeatHint')}>
            <NumberInput value={weeks} onChange={setWeeks} min={0} max={52} />
          </Field>
        </Group>
      )}
      {(fee > 0 || pending || resource?.maxHours) && (
        <Alert variant="light" color={pending ? 'orange' : 'violet'} icon={<IconInfoCircle size={18} />}>
          <Stack gap={2}>
            {fee > 0 && <Text size="sm">{t('booking.feeNote', { amount: chf(fee) })}</Text>}
            {pending && <Text size="sm">{t('booking.approvalNote')}</Text>}
            {resource?.maxHours && !manager ? <Text size="sm">{t('booking.maxHours', { count: resource.maxHours })}</Text> : null}
          </Stack>
        </Alert>
      )}
    </Modal>
  )
}

/** A booking in the calendar: who, when, and what the viewer may do. */
export function BookingDetail({ booking, options, onClose }: { booking: Booking; options: Options | undefined; onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const manager = !!options?.can.bookings
  const [series, setSeries] = useState(false)
  const [note, setNote] = useState('')
  const started = parseLocal(booking.startsAt) <= new Date()
  const canCancel = (manager || (booking.mine && !started)) && (booking.status === 'pending' || booking.status === 'approved')
  const decide = manager && booking.status === 'pending'

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    if (await run(fn, ok)) {
      qc.invalidateQueries({ queryKey: QK.all })
      onClose()
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={booking.title || booking.resourceName || t('booking.booking')}
      footer={
        <>
          {decide ? (
            <Button color="red" variant="subtle" mr="auto" loading={busy} onClick={() => act(() => decideBooking(booking.id, false, note || undefined), t('booking.rejected'))}>
              {t('booking.reject')}
            </Button>
          ) : (
            canCancel && (
              <Button color="red" variant="subtle" mr="auto" loading={busy} onClick={() => act(() => cancelBooking(booking.id, series), t('booking.cancelled'))}>
                {t('booking.cancelBooking')}
              </Button>
            )
          )}
          <Button variant="default" onClick={onClose}>
            {t('booking.close')}
          </Button>
          {decide && (
            <Button loading={busy} onClick={() => act(() => decideBooking(booking.id, true, note || undefined), t('booking.approved'))}>
              {t('booking.approve')}
            </Button>
          )}
        </>
      }
    >
      <Stack gap="xs">
        <Group gap="xs">
          <Badge variant="light" color={STATUS_COLOR[booking.status]} style={{ textTransform: 'none' }}>
            {t(`booking.status.${booking.status}`)}
          </Badge>
          {booking.seriesId && (
            <Badge variant="light" color="gray" style={{ textTransform: 'none' }}>
              {t('booking.weekly')}
            </Badge>
          )}
        </Group>
        <Text>
          <b>{booking.resourceName}</b> · {when(booking)}
        </Text>
        <Text size="sm" c="dimmed">
          {t('booking.bookedBy', { name: booking.memberName ?? '–' })}
        </Text>
        {booking.note && <Text size="sm">{booking.note}</Text>}
        {booking.fee ? <Text size="sm">{t('booking.feeNote', { amount: chf(booking.fee) })}</Text> : null}
        {booking.decisionNote && (
          <Text size="sm" c="dimmed">
            {t('booking.decisionNote', { note: booking.decisionNote })}
          </Text>
        )}
        {decide && (
          <Field label={t('booking.decisionField')}>
            <TextInput value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          </Field>
        )}
        {canCancel && booking.seriesId && (
          <Checkbox checked={series} onChange={(e) => setSeries(e.currentTarget.checked)} label={t('booking.cancelSeries')} />
        )}
      </Stack>
    </Modal>
  )
}
