import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Box, Button, Group, NumberInput, Paper, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Textarea } from '@mantine/core'
import { IconBuilding, IconPlus, IconTool } from '@tabler/icons-react'
import { ConfirmModal, EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import { OUT_OF_USE, QK, deleteResource, errorText, listInventoryItems, listResources, saveResource, type Kind, type Options, type Resource } from './api'
import { CategoryField, chf, useAction } from './common'
import { resourceColor } from './CalendarTab'

const COLORS = ['violet', 'blue', 'cyan', 'teal', 'green', 'yellow', 'orange', 'red', 'pink', 'grape']

function Dot({ color, size }: { color: string; size: number }) {
  return <Box style={{ width: size, height: size, borderRadius: '50%', flexShrink: 0, background: `var(--mantine-color-${color}-filled)` }} />
}

/** Rooms and equipment, for those who manage them. */
export function ResourcesTab({ options }: { options: Options | undefined }) {
  const { t } = useT()
  const resources = useQuery({ queryKey: QK.resources(true), queryFn: () => listResources(true) })
  const [editing, setEditing] = useState<Resource | 'new' | null>(null)

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap">
        <Text size="sm" c="dimmed">
          {t(options?.inventory ? 'booking.resources.hintInventory' : 'booking.resources.hint')}
        </Text>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
          {t('booking.resources.new')}
        </Button>
      </Group>
      {resources.error ? (
        <ErrorBanner message={errorText(resources.error)} onRetry={() => resources.refetch()} />
      ) : resources.isLoading ? (
        <LoadingSpinner />
      ) : !resources.data?.length ? (
        <EmptyState icon={<IconBuilding size={28} />} title={t('booking.resources.none')} description={t('booking.resources.noneHint')} />
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {resources.data.map((r) => (
            <Paper key={r.id} withBorder p="md" radius="md" style={{ cursor: 'pointer', opacity: r.active ? 1 : 0.6 }} onClick={() => setEditing(r)}>
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                  <Dot color={resourceColor(r)} size={12} />
                  <Text fw={600} truncate>
                    {r.name}
                  </Text>
                </Group>
                <Badge variant="light" color="gray" leftSection={r.kind === 'room' ? <IconBuilding size={12} /> : <IconTool size={12} />} style={{ textTransform: 'none', flexShrink: 0 }}>
                  {t(`booking.kinds.${r.kind}`)}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed" mt={4}>
                {[
                  r.location,
                  r.feeFlat || r.feePerHour
                    ? [r.feeFlat ? chf(r.feeFlat) : null, r.feePerHour ? t('booking.perHour', { amount: chf(r.feePerHour) }) : null].filter(Boolean).join(' + ')
                    : t('booking.free'),
                  r.inventoryItemName ? (r.inventoryItemName === r.name ? t('booking.resources.pickItem') : t('booking.resources.linked', { name: r.inventoryItemName })) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
              <Group gap={6} mt={6}>
                {r.needsApproval && (
                  <Badge size="sm" variant="light" color="orange" style={{ textTransform: 'none' }}>
                    {t('booking.needsApproval')}
                  </Badge>
                )}
                {options?.inventory && r.kind === 'equipment' && !r.inventoryItemId && (
                  <Badge size="sm" variant="light" color="yellow" style={{ textTransform: 'none' }}>
                    {t('booking.resources.notInInventory')}
                  </Badge>
                )}
                {r.inventoryItemStatus && OUT_OF_USE.includes(r.inventoryItemStatus) && (
                  <Badge size="sm" variant="light" color="red" style={{ textTransform: 'none' }}>
                    {t('booking.resources.outOfUse')}
                  </Badge>
                )}
                {!r.active && (
                  <Badge size="sm" variant="light" color="gray" style={{ textTransform: 'none' }}>
                    {t('booking.resources.off')}
                  </Badge>
                )}
              </Group>
            </Paper>
          ))}
        </SimpleGrid>
      )}
      {editing && <ResourceModal resource={editing === 'new' ? null : editing} options={options} onClose={() => setEditing(null)} />}
    </Stack>
  )
}

function ResourceModal({ resource, options, onClose }: { resource: Resource | null; options: Options | undefined; onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const items = useQuery({ queryKey: QK.items, queryFn: listInventoryItems, enabled: !!options?.inventory })
  const [name, setName] = useState(resource?.name ?? '')
  const [kind, setKind] = useState<Kind>(resource?.kind ?? 'room')
  const [location, setLocation] = useState(resource?.location ?? '')
  const [description, setDescription] = useState(resource?.description ?? '')
  const [color, setColor] = useState(resource?.color ?? 'violet')
  const [itemId, setItemId] = useState<number | null>(resource?.inventoryItemId ?? null)
  const [needsApproval, setNeedsApproval] = useState(resource?.needsApproval ?? false)
  const [feeFlat, setFeeFlat] = useState<number | string>(resource?.feeFlat ?? '')
  const [feePerHour, setFeePerHour] = useState<number | string>(resource?.feePerHour ?? '')
  const [categoryId, setCategoryId] = useState<number | null>(resource?.categoryId ?? null)
  const [maxHours, setMaxHours] = useState<number | string>(resource?.maxHours ?? '')
  const [advanceDays, setAdvanceDays] = useState<number | string>(resource?.advanceDays ?? '')
  const [active, setActive] = useState(resource?.active ?? true)
  const [deleting, setDeleting] = useState(false)
  // With Inventory running, equipment is an inventory item: its name and
  // place come from there. A room may be one too.
  const fromInventory = !!options?.inventory && kind === 'equipment'
  const item = items.data?.find((i) => i.id === itemId)
  const itemOptions = (items.data ?? []).map((i) => {
    const taken = i.resourceId != null && i.resourceId !== resource?.id
    const label = [i.name, i.location ? `(${i.location})` : null, taken ? `· ${t('booking.resources.itemTaken')}` : null].filter(Boolean).join(' ')
    return { value: String(i.id), label, disabled: taken }
  })
  const pickItem = (v: string | null) => {
    const id = v ? Number(v) : null
    setItemId(id)
    const picked = items.data?.find((i) => i.id === id)
    if (picked) {
      setName(picked.name)
      if (picked.location) setLocation(picked.location)
    }
  }

  const done = () => {
    qc.invalidateQueries({ queryKey: QK.all })
    onClose()
  }
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    const body = {
      name,
      kind,
      location,
      description,
      color,
      inventoryItemId: itemId,
      needsApproval,
      feeFlat: feeFlat === '' ? null : feeFlat,
      feePerHour: feePerHour === '' ? null : feePerHour,
      categoryId,
      maxHours: maxHours === '' ? null : maxHours,
      advanceDays: advanceDays === '' ? null : advanceDays,
      active,
    }
    if (await run(() => saveResource(body, resource?.id), t('booking.saved'))) done()
  }

  return (
    <Modal
      open
      wide
      onClose={onClose}
      onSubmit={submit}
      title={resource ? t('booking.resources.edit') : t('booking.resources.new')}
      footer={
        <>
          {resource && (
            <Button color="red" variant="subtle" mr="auto" onClick={() => setDeleting(true)}>
              {t('booking.delete')}
            </Button>
          )}
          <Button variant="default" onClick={onClose}>
            {t('booking.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={fromInventory ? !itemId : !name.trim()}>
            {t('booking.save')}
          </Button>
        </>
      }
    >
      <Field label={t('booking.resources.kind')}>
        <SegmentedControl
          fullWidth
          value={kind}
          onChange={(v) => setKind(v as Kind)}
          data={[
            { value: 'room', label: t('booking.kinds.room') },
            { value: 'equipment', label: t('booking.kinds.equipment') },
          ]}
        />
      </Field>
      {fromInventory ? (
        <Field label={t('booking.resources.pickItem')} hint={t('booking.resources.pickItemHint')}>
          <Select
            aria-label={t('booking.resources.pickItem')}
            placeholder={t('booking.resources.pickItemPlaceholder')}
            data={itemOptions}
            value={itemId ? String(itemId) : null}
            onChange={pickItem}
            searchable
            data-autofocus
          />
        </Field>
      ) : (
        <Field label={t('booking.resources.name')}>
          <TextInput value={item ? item.name : name} disabled={!!item} onChange={(e) => setName(e.currentTarget.value)} placeholder={t('booking.resources.nameExample')} data-autofocus />
        </Field>
      )}
      <Group grow align="flex-start">
        <Field label={t('booking.resources.location')}>
          <TextInput value={item?.location ? item.location : location} disabled={!!item?.location} onChange={(e) => setLocation(e.currentTarget.value)} />
        </Field>
        <Field label={t('booking.resources.color')}>
          <Group gap={6} mt={6}>
            {COLORS.map((c) => (
              <Box
                key={c}
                component="button"
                type="button"
                aria-label={c}
                aria-pressed={color === c}
                onClick={() => setColor(c)}
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  border: 0,
                  padding: 0,
                  cursor: 'pointer',
                  background: `var(--mantine-color-${c}-filled)`,
                  outline: color === c ? '2px solid var(--mantine-color-text)' : undefined,
                  outlineOffset: 2,
                }}
              />
            ))}
          </Group>
        </Field>
      </Group>
      <Field label={t('booking.resources.description')}>
        <Textarea value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
      </Field>
      {options?.inventory && !fromInventory && (
        <Field label={t('booking.resources.item')} hint={t('booking.resources.itemHint')}>
          <Select aria-label={t('booking.resources.item')} data={itemOptions} value={itemId ? String(itemId) : null} onChange={pickItem} clearable searchable />
        </Field>
      )}
      <Group grow align="flex-start">
        <Field label={t('booking.resources.feeFlat')}>
          <NumberInput value={feeFlat} onChange={setFeeFlat} min={0} decimalScale={2} leftSection="CHF" leftSectionWidth={44} />
        </Field>
        <Field label={t('booking.resources.feePerHour')}>
          <NumberInput value={feePerHour} onChange={setFeePerHour} min={0} decimalScale={2} leftSection="CHF" leftSectionWidth={44} />
        </Field>
      </Group>
      {(feeFlat !== '' || feePerHour !== '') && <CategoryField value={categoryId} onChange={setCategoryId} options={options} />}
      <Group grow align="flex-start">
        <Field label={t('booking.resources.maxHours')} hint={t('booking.resources.maxHoursHint')}>
          <NumberInput value={maxHours} onChange={setMaxHours} min={1} max={744} />
        </Field>
        <Field label={t('booking.resources.advanceDays')} hint={t('booking.resources.advanceDaysHint')}>
          <NumberInput value={advanceDays} onChange={setAdvanceDays} min={1} max={3650} />
        </Field>
      </Group>
      <Stack gap="xs">
        <Switch checked={needsApproval} onChange={(e) => setNeedsApproval(e.currentTarget.checked)} label={t('booking.resources.needsApproval')} />
        {resource && <Switch checked={active} onChange={(e) => setActive(e.currentTarget.checked)} label={t('booking.resources.active')} />}
      </Stack>
      <ConfirmModal
        open={deleting}
        title={t('booking.resources.deleteTitle')}
        body={resource?.name ?? ''}
        confirmLabel={t('booking.delete')}
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          setDeleting(false)
          if (resource && (await run(() => deleteResource(resource.id)))) done()
        }}
      />
    </Modal>
  )
}
