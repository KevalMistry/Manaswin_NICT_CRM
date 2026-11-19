import { useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../services/api'
import type { AuthResponse } from '../types'

function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [forgotMessage, setForgotMessage] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsLoading(true)
    try {
      const { data } = await api.post<AuthResponse>('/api/auth/login', { email, password })
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('current_user', JSON.stringify(data.user))
      const destination = location.state?.from?.pathname ?? (data.user.role_name === 'Student' ? '/portal' : '/dashboard')
      navigate(destination, { replace: true })
    } catch (requestError) {
      setPassword('')
      if (axios.isAxiosError(requestError)) {
        const detail = requestError.response?.data?.detail
        if (typeof detail === 'string') {
          setError(detail)
        } else if (Array.isArray(detail)) {
          setError(detail.map((item) => item.msg).filter(Boolean).join(', ') || 'Please check your email and password.')
        } else if (!requestError.response) {
          setError('Unable to connect to the backend. Confirm that FastAPI is running on port 8000.')
        } else if (requestError.response.status === 401) {
          setError('Invalid email or password.')
        } else if (requestError.response.status === 422) {
          setError('Please enter a valid email address and password.')
        } else {
          setError(`Login failed (HTTP ${requestError.response.status}). Please try again.`)
        }
      } else {
        setError('Unable to connect to the backend. Confirm that FastAPI is running on port 8000.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function requestReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsLoading(true)
    setError('')
    setForgotMessage('')
    try {
      const { data } = await api.post<{ message: string }>('/api/auth/forgot-password', { email })
      setForgotMessage(data.message)
    } catch (requestError) {
      setError(axios.isAxiosError(requestError) && typeof requestError.response?.data?.detail === 'string' ? requestError.response.data.detail : 'Unable to send the reset email.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-visual">
        <div className="visual-glow glow-one" />
        <div className="visual-glow glow-two" />
        <div className="login-brand"><div className="brand-mark">N</div><strong>NICT</strong></div>
        <div className="visual-content">
          <span className="eyebrow">INSTITUTE MANAGEMENT PLATFORM</span>
          <h1>One clear view<br />of your <em>institute.</em></h1>
          <p>Manage people, programs, performance, and progress from one connected workspace.</p>
        </div>
        <div className="visual-footer">© 2026 NICT Institute Management <span>●</span> Built for growth</div>
      </div>
      <div className="login-panel">
        <div className="login-form-wrap">
          <div className="mobile-login-brand"><div className="brand-mark">N</div><strong>NICT</strong></div>
          <span className="eyebrow">WELCOME BACK</span>
          <h2>Sign in to your workspace</h2>
          <p className="muted">Enter your credentials to continue to the admin portal.</p>
          <form onSubmit={submit}>
            <label htmlFor="email">Email address</label>
            <input id="email" type="email" autoComplete="email" placeholder="you@institute.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <div className="label-row"><label htmlFor="password">Password</label><button className="text-link" onClick={() => setForgotOpen(true)} type="button">Forgot password?</button></div>
            <div className="password-input"><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} required /><button aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)} type="button">{showPassword ? 'Hide' : 'Show'}</button></div>
            {error && <div className="form-error">{error}</div>}
            <button className="primary-button login-button" disabled={isLoading} type="submit">{isLoading ? 'Signing in…' : 'Sign in'} <span>→</span></button>
          </form>
          <p className="form-footer">New student? <a href="/admission">Apply online</a> · Need access? <a href="mailto:admin@nict.local">Contact your administrator</a></p>
        </div>
      </div>
      {forgotOpen && <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true"><div className="modal-header"><div><span className="eyebrow">ACCOUNT RECOVERY</span><h2>Reset your password</h2></div><button className="close-button" onClick={() => setForgotOpen(false)} type="button">×</button></div><p className="muted">Enter your account email and we will send a secure reset link.</p><form className="settings-form" onSubmit={requestReset}><div className="field"><label htmlFor="forgot-email">Email address</label><input id="forgot-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>{forgotMessage && <div className="success-message">{forgotMessage}</div>}{error && <div className="form-error">{error}</div>}<button className="primary-button" disabled={isLoading} type="submit">{isLoading ? 'Sending…' : 'Send reset link'}</button></form></div></div>}
    </div>
  )
}

export default LoginPage
