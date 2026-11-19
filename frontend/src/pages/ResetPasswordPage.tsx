import { useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '../services/api'

function ResetPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (password !== confirmation) {
      setError('Passwords do not match.')
      return
    }
    try {
      const { data } = await api.post<{ message: string }>('/api/auth/reset-password', { token: params.get('token'), new_password: password })
      setMessage(data.message)
    } catch (requestError) {
      setError(axios.isAxiosError(requestError) && typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : 'Unable to reset your password.')
    }
  }

  return <div className="login-page"><div className="login-panel"><div className="login-form-wrap"><span className="eyebrow">ACCOUNT RECOVERY</span><h2>Choose a new password</h2><p className="muted">Your new password must contain at least 8 characters.</p>{message ? <><div className="success-message">{message}</div><button className="primary-button login-button" onClick={() => navigate('/login')} type="button">Return to sign in</button></> : <form onSubmit={submit}><label htmlFor="reset-password">New password</label><div className="password-input"><input id="reset-password" type={showPassword ? 'text' : 'password'} minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /><button aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)} type="button">{showPassword ? 'Hide' : 'Show'}</button></div><label htmlFor="reset-confirm">Confirm password</label><input id="reset-confirm" type={showPassword ? 'text' : 'password'} minLength={8} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />{error && <div className="form-error">{error}</div>}<button className="primary-button login-button" type="submit">Set new password <span>→</span></button></form>}</div></div></div>
}

export default ResetPasswordPage
