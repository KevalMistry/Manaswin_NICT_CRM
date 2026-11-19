import { Navigate, Outlet } from 'react-router-dom'
import { getStoredUser } from '../utils/auth'

type ProtectedRouteProps = {
  allowedRoles?: string[]
  requiredModule?: string
}

function ProtectedRoute({ allowedRoles, requiredModule }: ProtectedRouteProps) {
  const token = localStorage.getItem('access_token')
  const user = getStoredUser()
  const roleAllowed = !allowedRoles || (user?.role_name ? allowedRoles.includes(user.role_name) : false)
  const isSuperAdmin = user?.role_name === 'Super Admin'
  const moduleAllowed =
    !requiredModule || isSuperAdmin || (user?.allowed_modules ?? []).includes(requiredModule)

  if (!token) {
    return <Navigate to="/login" replace />
  }
  if (!roleAllowed) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    return <Navigate to="/login" replace />
  }
  if (!moduleAllowed) {
    const destination = user?.role_name === 'Student' ? '/portal' : '/dashboard'
    return <Navigate to={destination} replace />
  }
  return <Outlet />
}

export default ProtectedRoute
