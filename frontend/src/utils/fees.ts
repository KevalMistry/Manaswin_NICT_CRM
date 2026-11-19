import { addMonthsInputValue } from './date'

export type FeePlanRow = { amount: string; dueDate: string }

/**
 * Split a net fee into equal installments without losing paise and place each
 * installment one month apart. Leftover paise go on the earliest installments.
 */
export function buildFeePlanRows(
  net: number,
  count: number,
  firstDueDate: string,
): FeePlanRow[] {
  if (!Number.isFinite(net) || net <= 0 || !firstDueDate || count < 1) return []
  const totalPaise = Math.round(net * 100)
  const base = Math.floor(totalPaise / count)
  const remainder = totalPaise - base * count
  return Array.from({ length: count }, (_, index) => ({
    amount: ((base + (index < remainder ? 1 : 0)) / 100).toFixed(2),
    dueDate: addMonthsInputValue(firstDueDate, index),
  }))
}
