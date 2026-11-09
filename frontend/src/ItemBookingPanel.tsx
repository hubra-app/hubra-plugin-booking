import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Group, SimpleGrid, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { PanelField, PanelSection, useT } from '@hubra/plugin-sdk'
import { OUT_OF_USE, QK, getOptions, getResourceByItem } from './api'
import { chf } from './common'
import { ResourceModal } from './ResourcesTab'

/**
 * On an inventory item's page: whether members can book it, at what fee and
 * with whose approval, and a link to its calendar. Those who manage resources
 * make the item bookable here, so equipment is set up where it is described.
 */
export function ItemBookingPanel({ itemId }: { itemId: number }) {
  const { t } = useT()
  const [editing, setEditing] = useState(false)
  const data = useQuery({ queryKey: QK.byItem(itemId), queryFn: () => getResourceByItem(itemId), retry: false })
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions, enabled: !!data.data?.canManage })
  const r = data.data?.resource
  const item = data.data?.item
  if (!data.data || !item || (!r && !data.data.canManage)) return null

  const fee = r && (r.feeFlat || r.feePerHour)
    ? [r.feeFlat ? chf(r.feeFlat) : null, r.feePerHour ? t('booking.perHour', { amount: chf(r.feePerHour) }) : null].filter(Boolean).join(' + ')
    : t('booking.free')
  const outOfUse = !!item.status && OUT_OF_USE.includes(item.status)

  return (
    <>
      <PanelSection
        label={t('booking.item.panel')}
        right={
          data.data.canManage && r ? (
            <Button size="compact-xs" variant="subtle" onClick={() => setEditing(true)}>
              {t('booking.item.edit')}
            </Button>
          ) : null
        }
      >
        {!r ? (
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text size="sm" c="dimmed">
              {t('booking.item.notBookable')}
            </Text>
            <Button size="xs" onClick={() => setEditing(true)}>
              {t('booking.item.makeBookable')}
            </Button>
          </Group>
        ) : (
          <>
            <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="sm">
              <PanelField label={t('booking.item.fee')}>{fee}</PanelField>
              <PanelField label={t('booking.item.approval')}>{r.needsApproval ? t('booking.needsApproval') : t('booking.item.noApproval')}</PanelField>
              <PanelField label={t('booking.item.limits')}>
                {[
                  r.maxHours ? t('booking.item.maxHours', { n: r.maxHours }) : null,
                  t('booking.item.ahead', { n: r.advanceDays ?? 180 }),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </PanelField>
            </SimpleGrid>
            {r.description && (
              <Text size="sm" mt="sm" style={{ whiteSpace: 'pre-wrap' }}>
                {r.description}
              </Text>
            )}
            <Group gap="xs" mt="sm" wrap="wrap">
              {!r.active && (
                <Badge variant="light" color="gray" style={{ textTransform: 'none' }}>
                  {t('booking.resources.off')}
                </Badge>
              )}
              {outOfUse && (
                <Badge variant="light" color="red" style={{ textTransform: 'none' }}>
                  {t('booking.resources.outOfUse')}
                </Badge>
              )}
              {r.active && !outOfUse && (
                <Button size="xs" variant="light" component={Link} to={`/app/booking?resource=${r.id}`}>
                  {t('booking.item.calendar')}
                </Button>
              )}
            </Group>
          </>
        )}
      </PanelSection>
      {editing && (
        <ResourceModal
          resource={r ?? null}
          options={options.data}
          fixedItem={{ id: item.id, name: item.name, location: item.location }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  )
}
