import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import api from '../services/api'
import type { User } from '../types'
import { getStoredUser, storeUser, USER_UPDATED_EVENT } from '../utils/auth'
import AuthImage from '../components/AuthImage'

type NavItem = {
  label: string
  path: string
  icon: string
  moduleKey?: string
  allowedRoles?: string[]
}

const navigation: NavItem[] = [
  { label: 'Overview', path: '/dashboard', icon: '⌂' },
  { label: 'Branches', path: '/branches', icon: '◫', moduleKey: 'branches' },
  { label: 'Students', path: '/students', icon: '♙', moduleKey: 'students' },
  { label: 'Courses & Batches', path: '/courses', icon: '▦', moduleKey: 'courses' },
  { label: 'Staff & Performance', path: '/staff', icon: '♟', moduleKey: 'staff' },
  { label: 'Enrollments', path: '/enrollments', icon: '↗', moduleKey: 'enrollments' },
  { label: 'Admissions', path: '/admissions', icon: '▤', allowedRoles: ['Super Admin', 'Branch Admin', 'Staff', 'Counsellor'] },
  { label: 'Enquiries', path: '/enquiries', icon: '☎', moduleKey: 'enquiries' },
  { label: 'Fees', path: '/fees', icon: '₹', moduleKey: 'fees' },
  { label: 'Attendance', path: '/attendance', icon: '✓', moduleKey: 'attendance' },
  { label: 'Examinations', path: '/examinations', icon: '▤', moduleKey: 'examinations' },
  { label: 'Online Exams', path: '/online-exams', icon: '◷', moduleKey: 'examinations' },
  { label: 'Certificates', path: '/certificates', icon: '◇', moduleKey: 'certificates' },
  { label: 'Learning', path: '/lms', icon: '▤', moduleKey: 'lms' },
  { label: 'Notifications', path: '/notifications', icon: '✉', moduleKey: 'notifications' },
  { label: 'Email Templates', path: '/email-templates', icon: '✉', moduleKey: 'notifications' },
  { label: 'Placement Cell', path: '/placement', icon: '⌂', moduleKey: 'placement' },
  { label: 'Finance', path: '/finance', icon: '₹', moduleKey: 'finance' },
  { label: 'Franchises', path: '/franchises', icon: '◈', moduleKey: 'franchises' },
  { label: 'Reports', path: '/reports', icon: '▥', moduleKey: 'reports' },
  { label: 'Permissions', path: '/permissions', icon: '⚿', moduleKey: 'permissions' },
]

function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState<User>(() => getStoredUser() ?? ({} as User))
  const roleName = user.role_name ?? (user.role_id === 1 ? 'Super Admin' : user.role_id === 2 ? 'Branch Admin' : 'User')
  const isSuperAdmin = roleName === 'Super Admin'

  const [allowedModules, setAllowedModules] = useState<string[]>(() => {
    if (isSuperAdmin) return navigation.map((n) => n.moduleKey).filter(Boolean) as string[]
    return user.allowed_modules ?? [
      'students', 'courses', 'attendance', 'examinations', 'fees', 'enrollments', 'enquiries', 'staff', 'certificates', 'lms', 'notifications', 'reports'
    ]
  })
  const [accountOpen, setAccountOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setMenuOpen(false)
      setAccountOpen(false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [location.pathname])

  useEffect(() => {
    document.body.classList.toggle('nav-locked', menuOpen)
    return () => document.body.classList.remove('nav-locked')
  }, [menuOpen])

  useEffect(() => {
    // Refresh the topbar when the profile (and therefore the stored user) changes
    // without requiring a page reload.
    const refreshUser = () => setUser(getStoredUser() ?? ({} as User))
    window.addEventListener(USER_UPDATED_EVENT, refreshUser)
    window.addEventListener('storage', refreshUser)
    return () => {
      window.removeEventListener(USER_UPDATED_EVENT, refreshUser)
      window.removeEventListener('storage', refreshUser)
    }
  }, [])

  useEffect(() => {
    void api.get<{ allowed_modules: string[] }>('/api/permissions/my-permissions')
      .then(({ data }) => {
        setAllowedModules(data.allowed_modules)
        const updated = getStoredUser()
        if (updated) {
          updated.allowed_modules = data.allowed_modules
          storeUser(updated)
        }
      })
      .catch(() => {})
  }, [])

  const visibleNavigation = navigation.filter((item) => {
    if (item.allowedRoles && !item.allowedRoles.includes(roleName)) return false
    if (!item.moduleKey) return true
    if (isSuperAdmin) return true
    return allowedModules.includes(item.moduleKey)
  })

  function logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar${menuOpen ? ' sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <strong>NICT</strong>
            <span>Institute OS</span>
          </div>
          <button
            className="sidebar-close"
            onClick={() => setMenuOpen(false)}
            type="button"
            aria-label="Close navigation"
          >
            ×
          </button>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="main-nav">
          {visibleNavigation.map((item) => (
            <NavLink
              className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
              key={item.path}
              onClick={() => setMenuOpen(false)}
              to={item.path}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="help-card">
            <span className="help-icon">?</span>
            <div>
              <strong>Need help?</strong>
              <small>Read the admin guide</small>
            </div>
          </div>
          <button className="logout-button" onClick={logout} type="button">
            <span>↪</span> Sign out
          </button>
        </div>
      </aside>
      {menuOpen && (
        <button
          aria-label="Close navigation"
          className="sidebar-overlay"
          onClick={() => setMenuOpen(false)}
          type="button"
        />
      )}
      <main className="main-content">
        <header className="topbar">
          <div className="topbar-lead">
            <button
              aria-expanded={menuOpen}
              aria-label="Open navigation"
              className="mobile-menu-button"
              onClick={() => setMenuOpen(true)}
              type="button"
            >
              ☰
            </button>
            <div className="breadcrumb">
              Workspace <span>/</span> {roleName}
            </div>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Notifications">◔</button>
            <button
              className="user-menu"
              onClick={() => setAccountOpen((open) => !open)}
              type="button"
              aria-expanded={accountOpen}
            >
              {user.profile_photo_url ? (
                <AuthImage
                  className="avatar profile-avatar"
                  path={user.profile_photo_url}
                  alt=""
                />
              ) : (
                <div className="avatar">{user.full_name?.slice(0, 1)?.toUpperCase() ?? 'A'}</div>
              )}
              <div className="user-copy">
                <strong>{user.full_name ?? 'Administrator'}</strong>
                <span>{user.email ?? 'admin@nict.local'}</span>
              </div>
              <span className="chevron">⌄</span>
            </button>
            {accountOpen && (
              <div className="account-menu">
                <strong>{user.full_name ?? 'Administrator'}</strong>
                <span>{roleName}</span>
                <span>{user.email ?? 'admin@nict.local'}</span>
                <button onClick={() => navigate('/profile')} type="button">Profile &amp; settings</button>
                <button onClick={() => navigate('/dashboard')} type="button">Dashboard</button>
                <button onClick={logout} type="button">Sign out</button>
              </div>
            )}
          </div>
        </header>
        <div className="page-content">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default AdminLayout
