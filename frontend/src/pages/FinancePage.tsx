import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser } from '../utils/auth'

type Summary = {
  fees_collected: string
  expenses: string
  net_income: string
  outstanding_fees: string
  gst_payable: string
  gst_rate_percent: number
  bank_balance: string
  active_bank_accounts: number
  expense_count: number
}

type Expense = {
  id: number
  branch_id: number
  branch_name: string
  category: string
  description: string
  amount: string
  gst_amount: string
  expense_date: string
  payment_method: string
  vendor: string | null
  reference: string | null
  notes: string | null
  receipt_url: string | null
  recorded_by: string | null
  created_at: string
}

type BankAccount = {
  id: number
  branch_id: number | null
  branch_name: string | null
  account_name: string
  bank_name: string
  account_number: string | null
  ifsc: string | null
  opening_balance: string
  is_active: boolean
  created_at: string
}

type CashEntry = {
  entry_date: string
  entry_type: string
  reference: string
  description: string
  category: string | null
  branch_name: string
  money_in: string
  money_out: string
}

type CashBook = {
  opening_balance: string
  closing_balance: string
  total_in: string
  total_out: string
  entries: CashEntry[]
}

type BranchOption = { id: number; name: string; code: string }

const CATEGORIES = [
  'Rent',
  'Salaries',
  'Utilities',
  'Marketing',
  'Maintenance',
  'Teaching Material',
  'Software',
  'Travel',
  'Royalty',
  'Miscellaneous',
]
const METHODS = ['Cash', 'UPI', 'Bank Transfer', 'Cheque', 'Card', 'Other']

function inr(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '₹0'
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function monthStart(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

function FinancePage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [accounts, setAccounts] = useState<BankAccount[]>([])
  const [cashBook, setCashBook] = useState<CashBook | null>(null)
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [tab, setTab] = useState<'expenses' | 'bank' | 'cashbook'>('expenses')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')

  const user = getStoredUser()
  const isSuperAdmin = user?.role_name === 'Super Admin'

  const [expenseForm, setExpenseForm] = useState({
    branch_id: '',
    category: 'Rent',
    description: '',
    amount: '',
    gst_amount: '',
    expense_date: today(),
    payment_method: 'Cash',
    vendor: '',
    reference: '',
    notes: '',
  })
  const [accountForm, setAccountForm] = useState({
    branch_id: '',
    account_name: '',
    bank_name: '',
    account_number: '',
    ifsc: '',
    opening_balance: '',
  })
  const [cashRange, setCashRange] = useState({
    date_from: monthStart(),
    date_to: today(),
  })
  const [categoryFilter, setCategoryFilter] = useState('all')

  const loadCore = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryRes, expenseRes, accountRes] = await Promise.all([
        api.get<Summary>('/api/finance/summary'),
        api.get<Expense[]>('/api/finance/expenses'),
        api.get<BankAccount[]>('/api/finance/bank-accounts'),
      ])
      setSummary(summaryRes.data)
      setExpenses(expenseRes.data)
      setAccounts(accountRes.data)
      if (isSuperAdmin) {
        try {
          const branchRes = await api.get<BranchOption[]>('/api/branches')
          setBranches(branchRes.data)
        } catch {
          setBranches([])
        }
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the finance module.'))
    } finally {
      setLoading(false)
    }
  }, [isSuperAdmin])

  const loadCashBook = useCallback(async (range: { date_from: string; date_to: string }) => {
    setError('')
    try {
      const params = new URLSearchParams()
      if (range.date_from) params.set('date_from', range.date_from)
      if (range.date_to) params.set('date_to', range.date_to)
      const { data } = await api.get<CashBook>(`/api/finance/cashbook?${params.toString()}`)
      setCashBook(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the cash book.'))
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCore(), 0)
    return () => window.clearTimeout(timer)
  }, [loadCore])

  useEffect(() => {
    if (tab !== 'cashbook') return
    const timer = window.setTimeout(() => void loadCashBook(cashRange), 0)
    return () => window.clearTimeout(timer)
  }, [tab, cashRange, loadCashBook])

  const filteredExpenses = useMemo(
    () =>
      categoryFilter === 'all'
        ? expenses
        : expenses.filter((expense) => expense.category === categoryFilter),
    [expenses, categoryFilter],
  )

  function flash(text: string) {
    setMessage(text)
    setError('')
  }

  function fail(requestError: unknown, fallback: string) {
    setError(apiErrorMessage(requestError, fallback))
    setMessage('')
  }

  async function addExpense(event: React.FormEvent) {
    event.preventDefault()
    setBusy('expense')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<Expense>('/api/finance/expenses', {
        branch_id: expenseForm.branch_id ? Number(expenseForm.branch_id) : null,
        category: expenseForm.category,
        description: expenseForm.description.trim(),
        amount: expenseForm.amount,
        gst_amount: expenseForm.gst_amount || '0',
        expense_date: expenseForm.expense_date,
        payment_method: expenseForm.payment_method,
        vendor: expenseForm.vendor.trim() || null,
        reference: expenseForm.reference.trim() || null,
        notes: expenseForm.notes.trim() || null,
      })
      setExpenses((current) => [data, ...current])
      setExpenseForm((current) => ({
        ...current,
        description: '',
        amount: '',
        gst_amount: '',
        vendor: '',
        reference: '',
        notes: '',
      }))
      flash(`Expense of ${inr(data.amount)} recorded.`)
      const summaryRes = await api.get<Summary>('/api/finance/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to save the expense.')
    } finally {
      setBusy('')
    }
  }

  async function deleteExpense(expense: Expense) {
    if (!window.confirm(`Delete expense “${expense.description}”?`)) return
    setBusy(`expense-${expense.id}`)
    setError('')
    try {
      await api.delete(`/api/finance/expenses/${expense.id}`)
      setExpenses((current) => current.filter((item) => item.id !== expense.id))
      flash('Expense removed.')
      const summaryRes = await api.get<Summary>('/api/finance/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to delete the expense.')
    } finally {
      setBusy('')
    }
  }

  async function addAccount(event: React.FormEvent) {
    event.preventDefault()
    setBusy('account')
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<BankAccount>('/api/finance/bank-accounts', {
        branch_id: accountForm.branch_id ? Number(accountForm.branch_id) : null,
        account_name: accountForm.account_name.trim(),
        bank_name: accountForm.bank_name.trim(),
        account_number: accountForm.account_number.trim() || null,
        ifsc: accountForm.ifsc.trim() || null,
        opening_balance: accountForm.opening_balance || '0',
      })
      setAccounts((current) => [...current, data])
      setAccountForm({
        branch_id: accountForm.branch_id,
        account_name: '',
        bank_name: '',
        account_number: '',
        ifsc: '',
        opening_balance: '',
      })
      flash(`${data.bank_name} account added.`)
      const summaryRes = await api.get<Summary>('/api/finance/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to save the bank account.')
    } finally {
      setBusy('')
    }
  }

  async function deleteAccount(account: BankAccount) {
    if (!window.confirm(`Remove ${account.bank_name} · ${account.account_name}?`)) return
    setBusy(`account-${account.id}`)
    setError('')
    try {
      await api.delete(`/api/finance/bank-accounts/${account.id}`)
      setAccounts((current) => current.filter((item) => item.id !== account.id))
      flash('Bank account removed.')
      const summaryRes = await api.get<Summary>('/api/finance/summary')
      setSummary(summaryRes.data)
    } catch (requestError) {
      fail(requestError, 'Unable to remove the bank account.')
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">FINANCE & ACCOUNTS</span>
          <h1>Income, expenses and cash book</h1>
          <p>
            Track fee income, branch expenses, bank balances and GST in one
            place. Figures respect your branch scope.
          </p>
        </div>
        <span className="result-count">
          GST {summary?.gst_rate_percent ?? 18}% inclusive
        </span>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="metric-grid finance-metrics">
        <article className="metric-card">
          <div className="metric-label">Fees collected</div>
          <div className="metric-value">{inr(summary?.fees_collected)}</div>
          <div className="metric-detail">All recorded payments</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Expenses</div>
          <div className="metric-value">{inr(summary?.expenses)}</div>
          <div className="metric-detail">{summary?.expense_count ?? 0} entries</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Net income</div>
          <div className="metric-value">{inr(summary?.net_income)}</div>
          <div className="metric-detail">Fees minus expenses</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Outstanding fees</div>
          <div className="metric-value">{inr(summary?.outstanding_fees)}</div>
          <div className="metric-detail">Receivable from students</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">GST payable</div>
          <div className="metric-value">{inr(summary?.gst_payable)}</div>
          <div className="metric-detail">Output less input GST</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">Cash &amp; bank</div>
          <div className="metric-value">{inr(summary?.bank_balance)}</div>
          <div className="metric-detail">
            {summary?.active_bank_accounts ?? 0} active accounts
          </div>
        </article>
      </section>

      <div className="module-tabs">
        <button
          className={tab === 'expenses' ? 'active-tab' : ''}
          onClick={() => setTab('expenses')}
          type="button"
        >
          Expenses <span>{expenses.length}</span>
        </button>
        <button
          className={tab === 'bank' ? 'active-tab' : ''}
          onClick={() => setTab('bank')}
          type="button"
        >
          Bank accounts <span>{accounts.length}</span>
        </button>
        <button
          className={tab === 'cashbook' ? 'active-tab' : ''}
          onClick={() => setTab('cashbook')}
          type="button"
        >
          Cash book
        </button>
      </div>

      {tab === 'expenses' && (
        <>
          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">RECORD EXPENSE</span>
                <h2>New branch expense</h2>
              </div>
            </div>
            <form className="placement-form-block" onSubmit={(event) => void addExpense(event)}>
              <div className="form-grid">
                {isSuperAdmin && (
                  <div className="field">
                    <label htmlFor="finance-expense-branch">Branch</label>
                    <select
                      id="finance-expense-branch"
                      onChange={(event) =>
                        setExpenseForm((current) => ({
                          ...current,
                          branch_id: event.target.value,
                        }))
                      }
                      value={expenseForm.branch_id}
                    >
                      <option value="">Select a branch</option>
                      {branches.map((branch) => (
                        <option key={branch.id} value={branch.id}>
                          {branch.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="finance-expense-category">Category</label>
                  <select
                    id="finance-expense-category"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        category: event.target.value,
                      }))
                    }
                    value={expenseForm.category}
                  >
                    {CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-description">Description</label>
                  <input
                    id="finance-expense-description"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    placeholder="e.g. October electricity bill"
                    required
                    value={expenseForm.description}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-amount">Amount (₹)</label>
                  <input
                    id="finance-expense-amount"
                    min={0}
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        amount: event.target.value,
                      }))
                    }
                    required
                    step="0.01"
                    type="number"
                    value={expenseForm.amount}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-gst">GST included (₹)</label>
                  <input
                    id="finance-expense-gst"
                    min={0}
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        gst_amount: event.target.value,
                      }))
                    }
                    step="0.01"
                    type="number"
                    value={expenseForm.gst_amount}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-date">Date</label>
                  <input
                    id="finance-expense-date"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        expense_date: event.target.value,
                      }))
                    }
                    required
                    type="date"
                    value={expenseForm.expense_date}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-method">Payment method</label>
                  <select
                    id="finance-expense-method"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        payment_method: event.target.value,
                      }))
                    }
                    value={expenseForm.payment_method}
                  >
                    {METHODS.map((method) => (
                      <option key={method} value={method}>
                        {method}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-vendor">Vendor</label>
                  <input
                    id="finance-expense-vendor"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        vendor: event.target.value,
                      }))
                    }
                    placeholder="Vendor / payee"
                    value={expenseForm.vendor}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-expense-reference">Bill reference</label>
                  <input
                    id="finance-expense-reference"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        reference: event.target.value,
                      }))
                    }
                    placeholder="Invoice or voucher number"
                    value={expenseForm.reference}
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="finance-expense-notes">Notes</label>
                  <textarea
                    id="finance-expense-notes"
                    onChange={(event) =>
                      setExpenseForm((current) => ({
                        ...current,
                        notes: event.target.value,
                      }))
                    }
                    rows={2}
                    value={expenseForm.notes}
                  />
                </div>
              </div>
              <div className="placement-form-actions">
                <button className="primary-button" disabled={busy === 'expense'} type="submit">
                  {busy === 'expense' ? 'Saving…' : 'Record expense'}
                </button>
              </div>
            </form>
          </section>

          <section className="data-panel finance-table-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">EXPENSE LEDGER</span>
                <h2>Recorded expenses</h2>
              </div>
              <div className="section-actions">
                <select
                  onChange={(event) => setCategoryFilter(event.target.value)}
                  value={categoryFilter}
                >
                  <option value="all">All categories</option>
                  {CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Category</th>
                    <th>Description</th>
                    <th>Vendor</th>
                    <th>Amount</th>
                    <th>GST</th>
                    <th>Branch</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filteredExpenses.map((expense) => (
                    <tr key={expense.id}>
                      <td>{expense.expense_date}</td>
                      <td>
                        <span className="exam-chip">{expense.category}</span>
                      </td>
                      <td>
                        <strong>{expense.description}</strong>
                        <small className="muted-block">
                          {expense.payment_method}
                          {expense.reference ? ` · ${expense.reference}` : ''}
                        </small>
                      </td>
                      <td>{expense.vendor ?? '—'}</td>
                      <td>{inr(expense.amount)}</td>
                      <td>{inr(expense.gst_amount)}</td>
                      <td>{expense.branch_name}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="danger-action"
                            disabled={busy === `expense-${expense.id}`}
                            onClick={() => void deleteExpense(expense)}
                            type="button"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filteredExpenses.length && (
                <div className="table-state">
                  {loading ? 'Loading expenses…' : 'No expenses recorded yet.'}
                </div>
              )}
            </div>
          </section>
        </>
      )}

      {tab === 'bank' && (
        <>
          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">BANK ACCOUNTS</span>
                <h2>Institution accounts</h2>
              </div>
            </div>
            <form className="placement-form-block" onSubmit={(event) => void addAccount(event)}>
              <div className="form-grid">
                {isSuperAdmin && (
                  <div className="field">
                    <label htmlFor="finance-account-branch">Branch</label>
                    <select
                      id="finance-account-branch"
                      onChange={(event) =>
                        setAccountForm((current) => ({
                          ...current,
                          branch_id: event.target.value,
                        }))
                      }
                      value={accountForm.branch_id}
                    >
                      <option value="">Head office (all branches)</option>
                      {branches.map((branch) => (
                        <option key={branch.id} value={branch.id}>
                          {branch.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="finance-account-name">Account name</label>
                  <input
                    id="finance-account-name"
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        account_name: event.target.value,
                      }))
                    }
                    required
                    value={accountForm.account_name}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-bank-name">Bank</label>
                  <input
                    id="finance-bank-name"
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        bank_name: event.target.value,
                      }))
                    }
                    required
                    value={accountForm.bank_name}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-account-number">Account number</label>
                  <input
                    id="finance-account-number"
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        account_number: event.target.value,
                      }))
                    }
                    value={accountForm.account_number}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-ifsc">IFSC</label>
                  <input
                    id="finance-ifsc"
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        ifsc: event.target.value,
                      }))
                    }
                    value={accountForm.ifsc}
                  />
                </div>
                <div className="field">
                  <label htmlFor="finance-opening">Opening balance (₹)</label>
                  <input
                    id="finance-opening"
                    min={0}
                    onChange={(event) =>
                      setAccountForm((current) => ({
                        ...current,
                        opening_balance: event.target.value,
                      }))
                    }
                    step="0.01"
                    type="number"
                    value={accountForm.opening_balance}
                  />
                </div>
              </div>
              <div className="placement-form-actions">
                <button className="primary-button" disabled={busy === 'account'} type="submit">
                  {busy === 'account' ? 'Saving…' : 'Add account'}
                </button>
              </div>
            </form>
          </section>

          <section className="data-panel finance-table-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">BALANCES</span>
                <h2>Bank accounts</h2>
              </div>
              <span className="result-count">{accounts.length} accounts</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Bank</th>
                    <th>Account</th>
                    <th>Number</th>
                    <th>IFSC</th>
                    <th>Opening balance</th>
                    <th>Branch</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id}>
                      <td>
                        <strong>{account.bank_name}</strong>
                      </td>
                      <td>{account.account_name}</td>
                      <td>{account.account_number ?? '—'}</td>
                      <td>{account.ifsc ?? '—'}</td>
                      <td>{inr(account.opening_balance)}</td>
                      <td>{account.branch_name ?? 'Head office'}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="danger-action"
                            disabled={busy === `account-${account.id}`}
                            onClick={() => void deleteAccount(account)}
                            type="button"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!accounts.length && (
                <div className="table-state">No bank accounts configured yet.</div>
              )}
            </div>
          </section>
        </>
      )}

      {tab === 'cashbook' && (
        <section className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">CASH BOOK</span>
              <h2>Money in and out</h2>
            </div>
            <div className="section-actions cashbook-range">
              <input
                onChange={(event) =>
                  setCashRange((current) => ({ ...current, date_from: event.target.value }))
                }
                type="date"
                value={cashRange.date_from}
              />
              <span className="muted">to</span>
              <input
                onChange={(event) =>
                  setCashRange((current) => ({ ...current, date_to: event.target.value }))
                }
                type="date"
                value={cashRange.date_to}
              />
            </div>
          </div>
          {cashBook && (
            <div className="cashbook-summary">
              <div>
                <span>Opening</span>
                <strong>{inr(cashBook.opening_balance)}</strong>
              </div>
              <div>
                <span>Money in</span>
                <strong className="positive">{inr(cashBook.total_in)}</strong>
              </div>
              <div>
                <span>Money out</span>
                <strong className="negative">{inr(cashBook.total_out)}</strong>
              </div>
              <div>
                <span>Closing</span>
                <strong>{inr(cashBook.closing_balance)}</strong>
              </div>
            </div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Reference</th>
                  <th>Description</th>
                  <th>Branch</th>
                  <th>In</th>
                  <th>Out</th>
                </tr>
              </thead>
              <tbody>
                {cashBook?.entries.map((entry) => (
                  <tr key={`${entry.entry_type}-${entry.reference}`}>
                    <td>{entry.entry_date}</td>
                    <td>
                      <span
                        className={`status-pill ${
                          entry.entry_type === 'income' ? 'active-status' : 'inactive-status'
                        }`}
                      >
                        <i />
                        {entry.entry_type === 'income' ? 'Income' : 'Expense'}
                      </span>
                    </td>
                    <td>{entry.reference}</td>
                    <td>
                      {entry.description}
                      {entry.category && (
                        <small className="muted-block">{entry.category}</small>
                      )}
                    </td>
                    <td>{entry.branch_name}</td>
                    <td>{entry.money_in === '0.00' ? '—' : inr(entry.money_in)}</td>
                    <td>{entry.money_out === '0.00' ? '—' : inr(entry.money_out)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cashBook && !cashBook.entries.length && (
              <div className="table-state">No transactions in this period.</div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}

export default FinancePage
