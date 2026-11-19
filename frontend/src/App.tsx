import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import ProtectedRoute from './components/ProtectedRoute'
import './App.css'
import { getStoredUser } from './utils/auth'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const BranchesPage = lazy(() => import('./pages/BranchesPage'))
const StudentsPage = lazy(() => import('./pages/StudentsPage'))
const CoursesPage = lazy(() => import('./pages/CoursesPage'))
const StaffPage = lazy(() => import('./pages/StaffPage'))
const EnrollmentsPage = lazy(() => import('./pages/EnrollmentsPage'))
const EnquiriesPage = lazy(() => import('./pages/EnquiriesPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const FeesPage = lazy(() => import('./pages/FeesPage'))
const AttendancePage = lazy(() => import('./pages/AttendancePage'))
const ExaminationsPage = lazy(() => import('./pages/ExaminationsPage'))
const OnlineExamsPage = lazy(() => import('./pages/OnlineExamsPage'))
const CertificatesPage = lazy(() => import('./pages/CertificatesPage'))
const CertificateVerificationPage = lazy(() =>
  import('./pages/CertificatesPage').then((module) => ({ default: module.CertificateVerificationPage })),
)
const LmsPage = lazy(() => import('./pages/LmsPage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const EmailTemplatesPage = lazy(() => import('./pages/EmailTemplatesPage'))
const PlacementPage = lazy(() => import('./pages/PlacementPage'))
const FinancePage = lazy(() => import('./pages/FinancePage'))
const FranchisePage = lazy(() => import('./pages/FranchisePage'))
const PermissionsPage = lazy(() => import('./pages/PermissionsPage'))
const AdmissionPage = lazy(() => import('./pages/AdmissionPage'))
const AdmissionsPage = lazy(() => import('./pages/AdmissionsPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const StudentPortalPage = lazy(() => import('./pages/StudentPortalPage'))
const PortalPage = lazy(() => import('./pages/PortalPage'))

function AuthenticatedHomeRedirect() {
  const user = getStoredUser()
  if (user?.role_name === 'Student') {
    return <Navigate to="/portal" replace />
  }
  return <Navigate to="/dashboard" replace />
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="page-loading" role="status">Loading…</div>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-certificate" element={<CertificateVerificationPage />} />
        <Route path="/admission" element={<AdmissionPage />} />

        {/* Shared student and parent portal */}
        <Route element={<ProtectedRoute allowedRoles={['Student']} />}>
          <Route path="/portal" element={<PortalPage />} />
          <Route path="/student/portal" element={<StudentPortalPage />} />
        </Route>

        {/* Workspace Layout */}
        <Route element={<ProtectedRoute allowedRoles={['Super Admin', 'Branch Admin', 'Faculty', 'Staff', 'Counsellor']} />}>
          <Route element={<AdminLayout />}>
            {/* Personalized Role Dashboards */}
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/admin/dashboard" element={<DashboardPage />} />
            <Route path="/branch-admin/dashboard" element={<DashboardPage />} />
            <Route path="/profile" element={<ProfilePage />} />

            {/* Modules with dynamic module permission guards */}
            <Route element={<ProtectedRoute requiredModule="branches" />}>
              <Route path="/branches" element={<BranchesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="students" />}>
              <Route path="/students" element={<StudentsPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="courses" />}>
              <Route path="/courses" element={<CoursesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="staff" />}>
              <Route path="/staff" element={<StaffPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="enrollments" />}>
              <Route path="/enrollments" element={<EnrollmentsPage />} />
            </Route>
            <Route element={<ProtectedRoute allowedRoles={['Super Admin', 'Branch Admin', 'Staff', 'Counsellor']} />}>
              <Route path="/admissions" element={<AdmissionsPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="enquiries" />}>
              <Route path="/enquiries" element={<EnquiriesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="fees" />}>
              <Route path="/fees" element={<FeesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="attendance" />}>
              <Route path="/attendance" element={<AttendancePage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="examinations" />}>
              <Route path="/examinations" element={<ExaminationsPage />} />
              <Route path="/online-exams" element={<OnlineExamsPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="certificates" />}>
              <Route path="/certificates" element={<CertificatesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="lms" />}>
              <Route path="/lms" element={<LmsPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="notifications" />}>
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/email-templates" element={<EmailTemplatesPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="placement" />}>
              <Route path="/placement" element={<PlacementPage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="finance" />}>
              <Route path="/finance" element={<FinancePage />} />
            </Route>

            <Route element={<ProtectedRoute allowedRoles={['Super Admin']} requiredModule="franchises" />}>
              <Route path="/franchises" element={<FranchisePage />} />
            </Route>

            <Route element={<ProtectedRoute requiredModule="reports" />}>
              <Route path="/reports" element={<ReportsPage />} />
            </Route>

            <Route element={<ProtectedRoute allowedRoles={['Super Admin', 'Branch Admin']} requiredModule="permissions" />}>
              <Route path="/permissions" element={<PermissionsPage />} />
            </Route>
          </Route>
        </Route>

        <Route
          path="*"
          element={localStorage.getItem('access_token') ? <AuthenticatedHomeRedirect /> : <Navigate to="/login" replace />}
        />
      </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
