/**
 * Format a date for an <input type="date"> in the user's local timezone.
 *
 * `Date#toISOString()` converts to UTC, which yields the previous day for
 * users east of UTC late in the evening (for example 00:30 IST).
 */
export function todayInputValue(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Add whole months to a YYYY-MM-DD input value, clamping the day to the last
 * day of the target month (for example 31 Jan + 1 month -> 28/29 Feb).
 */
export function addMonthsInputValue(value: string, months: number): string {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  const target = new Date(year, month - 1 + months, 1)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  target.setDate(Math.min(day, lastDay))
  return todayInputValue(target)
}
