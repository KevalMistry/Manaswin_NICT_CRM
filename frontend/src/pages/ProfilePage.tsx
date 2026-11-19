import { useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import type { User } from '../types'
import { getStoredUser, storeUser } from '../utils/auth'
import AuthImage from '../components/AuthImage'

function ProfilePage() {
  const navigate = useNavigate()
  const storedUser = getStoredUser() ?? ({} as User)
  const [profile, setProfile] = useState({
    full_name: storedUser.full_name ?? '',
    phone: storedUser.phone ?? '',
    profile_photo_url: storedUser.profile_photo_url ?? '',
  })
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState(storedUser.profile_photo_url ?? '')
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)
  const [showPasswords, setShowPasswords] = useState(false)

  function apiError(value: unknown, fallback: string) {
    if (axios.isAxiosError(value) && typeof value.response?.data?.detail === 'string') return value.response.data.detail
    return fallback
  }

  function selectPhoto(file: File | undefined) {
    if (!file) return
    setPhotoFile(file)
    setPhotoPreview(URL.createObjectURL(file))
  }

  async function uploadSelectedPhoto(file: File): Promise<User> {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post<User>('/api/auth/profile-photo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    storeUser(data)
    setProfile((current) => ({ ...current, profile_photo_url: data.profile_photo_url ?? '' }))
    setPhotoPreview(data.profile_photo_url ?? '')
    setPhotoFile(null)
    return data
  }

  async function uploadPhoto() {
    if (!photoFile) return
    setUploadingPhoto(true)
    setError('')
    setMessage('')
    try {
      await uploadSelectedPhoto(photoFile)
      setMessage('Profile photo updated successfully.')
    } catch (requestError) {
      setError(apiError(requestError, 'Unable to upload your profile photo.'))
    } finally {
      setUploadingPhoto(false)
    }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSavingProfile(true)
    setError('')
    setMessage('')
    try {
      let photoUrl = profile.profile_photo_url
      if (photoFile) {
        // Saving the profile also persists a newly selected photo, so users are
        // not required to press the separate upload button first.
        const uploaded = await uploadSelectedPhoto(photoFile)
        photoUrl = uploaded.profile_photo_url ?? ''
      }
      const { data } = await api.patch<User>('/api/auth/me', {
        ...profile,
        phone: profile.phone || null,
        profile_photo_url: photoUrl || null,
      })
      storeUser(data)
      setProfile((current) => ({ ...current, profile_photo_url: data.profile_photo_url ?? '' }))
      setPhotoPreview(data.profile_photo_url ?? '')
      setMessage('Profile updated successfully.')
    } catch (requestError) {
      setError(apiError(requestError, 'Unable to update your profile.'))
    } finally {
      setSavingProfile(false)
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (passwords.new_password !== passwords.confirm_password) {
      setError('New password and confirmation do not match.')
      return
    }
    setSavingPassword(true)
    try {
      await api.post('/api/auth/change-password', {
        current_password: passwords.current_password,
        new_password: passwords.new_password,
      })
      setPasswords({ current_password: '', new_password: '', confirm_password: '' })
      setMessage('Password changed successfully. Use the new password next time you sign in.')
    } catch (requestError) {
      setError(apiError(requestError, 'Unable to change your password.'))
    } finally {
      setSavingPassword(false)
    }
  }

  const initials = profile.full_name.slice(0, 1).toUpperCase() || 'A'

  return (
    <>
      <div className="page-heading module-heading"><div><span className="eyebrow">ACCOUNT</span><h1>Profile &amp; settings</h1><p>Manage your personal details, profile photo, and account security.</p></div><button className="secondary-button" onClick={() => navigate('/dashboard')} type="button">← Back to dashboard</button></div>
      {message && <div className="success-message">{message}</div>}
      {error && <div className="inline-error">{error}</div>}
      <div className="settings-grid">
        <section className="data-panel settings-card"><div className="section-title"><div><span className="eyebrow">PERSONAL DETAILS</span><h2>Your profile</h2></div></div><form className="settings-form" onSubmit={saveProfile}><div className="profile-preview">{photoPreview ? <AuthImage path={photoPreview} alt="Profile preview" /> : <span>{initials}</span>}<div><strong>{profile.full_name || 'Your name'}</strong><small>{storedUser.email}</small><small>{storedUser.role_id === 1 ? 'Super Admin' : 'Account user'}</small></div></div><div className="field"><label htmlFor="profile-photo">Profile photo</label><input id="profile-photo" type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={(event) => selectPhoto(event.target.files?.[0])} /><small className="field-hint">Choose a JPEG, PNG, GIF, or WebP image up to 5 MB.</small>{photoFile && <button className="secondary-button upload-photo-button" disabled={uploadingPhoto} onClick={uploadPhoto} type="button">{uploadingPhoto ? 'Uploading…' : 'Upload photo'}</button>}</div><div className="field"><label htmlFor="profile-name">Full name</label><input id="profile-name" value={profile.full_name} onChange={(event) => setProfile({ ...profile, full_name: event.target.value })} required /></div><div className="field"><label htmlFor="profile-phone">Phone</label><input id="profile-phone" value={profile.phone} onChange={(event) => setProfile({ ...profile, phone: event.target.value })} placeholder="+91…" /></div><button className="primary-button" disabled={savingProfile} type="submit">{savingProfile ? 'Saving…' : 'Save profile'}</button></form></section>
        <section className="data-panel settings-card"><div className="section-title"><div><span className="eyebrow">SECURITY</span><h2>Change password</h2></div></div><form className="settings-form" onSubmit={changePassword}><div className="field"><label htmlFor="current-password">Current password</label><div className="password-input"><input id="current-password" type={showPasswords ? 'text' : 'password'} value={passwords.current_password} onChange={(event) => setPasswords({ ...passwords, current_password: event.target.value })} required /><button onClick={() => setShowPasswords((value) => !value)} type="button">{showPasswords ? 'Hide' : 'Show'}</button></div></div><div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type={showPasswords ? 'text' : 'password'} minLength={8} value={passwords.new_password} onChange={(event) => setPasswords({ ...passwords, new_password: event.target.value })} required /><small className="field-hint">Use at least 8 characters.</small></div><div className="field"><label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type={showPasswords ? 'text' : 'password'} minLength={8} value={passwords.confirm_password} onChange={(event) => setPasswords({ ...passwords, confirm_password: event.target.value })} required /></div><button className="primary-button" disabled={savingPassword} type="submit">{savingPassword ? 'Updating…' : 'Update password'}</button></form><div className="security-note"><strong>Account security</strong><p>Your password is securely hashed and never displayed by the system.</p></div></section>
      </div>
    </>
  )
}

export default ProfilePage
