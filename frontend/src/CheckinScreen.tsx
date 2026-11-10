import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Checkbox, Group, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core'
import { IconCircleCheck, IconKey, IconMapPin } from '@tabler/icons-react'
import { ErrorBanner, LoadingSpinner, useT } from '@hubra/plugin-sdk'
import { checkIn, errorText, setOnsite, type CheckinResult } from './api'
import { useAction } from './common'
import { ONSITE_COLOR } from './OnsiteTab'

/** Opened from a room's QR code: the member is checked in there for today
 * (Vor Ort, "Bin da") and sees who else is there or coming. */
export function CheckinScreen() {
  const { t } = useT()
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const { busy, run } = useAction()
  const [result, setResult] = useState<CheckinResult | null>(null)
  const [error, setError] = useState<unknown>(null)
  const sent = useRef(false)

  const go = () => {
    setError(null)
    checkIn(token).then(setResult, setError)
  }
  useEffect(() => {
    // Once, also under React's double effects in development.
    if (sent.current) return
    sent.current = true
    go()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (error) return <ErrorBanner message={errorText(error)} onRetry={go} />
  if (!result) return <LoadingSpinner />
  const { room, entry, others, already } = result
  const keyHolder = entry.keyHolder
  const toggleKey = (on: boolean) =>
    run(() =>
      setOnsite({
        resourceId: room.id,
        day: entry.day,
        status: 'here',
        from: entry.from,
        to: entry.to,
        keyHolder: on,
        comment: entry.comment,
      }),
    ).then((ok) => {
      if (ok) setResult({ ...result, entry: { ...entry, keyHolder: on } })
    })

  return (
    <Stack maw={520} mx="auto" gap="md" py="md">
      <Paper withBorder radius="md" p="lg">
        <Stack align="center" gap="xs">
          <ThemeIcon size={56} radius="xl" color="violet" variant="light">
            <IconCircleCheck size={32} />
          </ThemeIcon>
          <Title order={2} ta="center">
            {already
              ? t('booking.checkin.already', { room: room.name })
              : t('booking.checkin.done', { room: room.name })}
          </Title>
          {room.location && (
            <Group gap={4}>
              <IconMapPin size={14} />
              <Text size="sm" c="dimmed">
                {room.location}
              </Text>
            </Group>
          )}
          <Text size="sm" c="dimmed" ta="center">
            {t('booking.checkin.hint')}
          </Text>
        </Stack>
      </Paper>
      <Paper withBorder radius="md" p="md">
        <Checkbox
          checked={keyHolder}
          disabled={busy}
          onChange={(e) => toggleKey(e.currentTarget.checked)}
          label={t('booking.onsite.keyHolder')}
          description={t('booking.checkin.keyHint')}
        />
      </Paper>
      <Paper withBorder radius="md" p="md">
        <Text fw={600} mb="xs">
          {t('booking.checkin.others')}
        </Text>
        {others.length ? (
          <Stack gap={6}>
            {others.map((o) => (
              <Group key={o.id} gap="xs" wrap="nowrap">
                <Badge
                  variant="light"
                  color={ONSITE_COLOR[o.status]}
                  style={{ textTransform: 'none', flexShrink: 0 }}
                >
                  {t(`booking.onsite.status.${o.status}`)}
                </Badge>
                <Text size="sm" truncate style={{ flex: 1 }}>
                  {o.memberName}
                  {o.from ? ` · ${o.from}${o.to ? `–${o.to}` : ''}` : ''}
                </Text>
                {o.keyHolder && <IconKey size={14} aria-label={t('booking.onsite.key')} />}
              </Group>
            ))}
          </Stack>
        ) : (
          <Text size="sm" c="dimmed">
            {t('booking.checkin.alone')}
          </Text>
        )}
      </Paper>
      <Button
        variant="light"
        onClick={() => navigate(`../booking/onsite?day=${entry.day}`, { relative: 'path' })}
      >
        {t('booking.checkin.toCalendar')}
      </Button>
    </Stack>
  )
}
