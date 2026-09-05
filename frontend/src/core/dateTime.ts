import type { UserPreferences } from '@/stores/auth'


type DateLike = string | number | Date | null | undefined

export function formatUserDateTime(
  value: DateLike,
  preferences?: UserPreferences | null,
): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }

  const timezone = preferences?.timezone?.trim()
  if (timezone && timezone.toLowerCase() !== 'system') {
    options.timeZone = timezone
  }

  if (preferences?.date_time_format === '12h') {
    options.hour12 = true
  } else if (preferences?.date_time_format === '24h') {
    options.hour12 = false
  }

  try {
    return new Intl.DateTimeFormat(undefined, options).format(date)
  } catch {
    // A legacy/invalid timezone must never break an operational table.
    delete options.timeZone
    return new Intl.DateTimeFormat(undefined, options).format(date)
  }
}

export function landingPath(
  page: UserPreferences['default_landing_page'] | null | undefined,
): string {
  switch (page) {
    case 'databases': return '/databases'
    case 'servers': return '/servers'
    case 'alerts': return '/alerts'
    default: return '/'
  }
}
