import { useState } from 'react'
import { Select } from '@mantine/core'
import { Field, formatCHF, useT, useToast } from '@hubra/plugin-sdk'
import { errorText, type Options } from './api'

export const chf = (amount: number | null | undefined) => `CHF ${formatCHF(amount ?? 0)}`

/** Runs an action with a busy flag and a toast for errors. */
export function useAction() {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try {
      await fn()
      if (ok) notify('success', ok)
      return true
    } catch (err) {
      notify('error', errorText(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, run }
}

/** The finance category a booking or invoice goes to. */
export function CategoryField({
  value,
  onChange,
  options,
  hint,
}: {
  value: number | null
  onChange: (id: number | null) => void
  options: Options | undefined
  hint?: string
}) {
  const { t } = useT()
  return (
    <Field label={t('booking.category')} hint={hint ?? t('booking.categoryHint')}>
      <Select
        aria-label={t('booking.category')}
        data={(options?.categories ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
        value={value ? String(value) : null}
        onChange={(id) => onChange(id ? Number(id) : null)}
        placeholder={t('booking.categoryNone')}
        clearable
        searchable
      />
    </Field>
  )
}
