import { Navigate } from 'react-router-dom'
import StudentPortalPage from './StudentPortalPage'
import { getStoredUser } from '../utils/auth'

function PortalPage() {
  const user = getStoredUser()

  if (user?.role_name === 'Student') {
    return <StudentPortalPage />
  }
  return <Navigate to="/dashboard" replace />
}

export default PortalPage
