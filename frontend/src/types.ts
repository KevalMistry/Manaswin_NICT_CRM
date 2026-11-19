export type User = {
  id: number
  full_name: string
  email: string
  role_id: number
  role_name: string
  branch_id: number | null
  phone: string | null
  profile_photo_url: string | null
  is_active: boolean
  allowed_modules?: string[]
}

export type AuthResponse = {
  access_token: string
  token_type: string
  user: User
}

export type ModulePermission = {
  module_key: string
  label: string
  can_access: boolean
}

export type RolePermission = {
  role_id: number
  role_name: string
  branch_id: number | null
  branch_name: string | null
  can_edit: boolean
  permissions: ModulePermission[]
}

export type MyPermissions = {
  role_name: string
  role_id: number
  branch_id: number | null
  branch_name: string | null
  can_manage_permissions: boolean
  allowed_modules: string[]
}

export type EnquiryStatus =
  | 'new_lead'
  | 'follow_up'
  | 'demo'
  | 'counselling'
  | 'admitted'
  | 'lost'

export type EnquirySource =
  | 'walk_in'
  | 'online'
  | 'website'
  | 'whatsapp'
  | 'facebook'
  | 'google_ads'
  | 'referral'
  | 'other'

export type Enquiry = {
  id: number
  enquiry_code: string
  full_name: string
  email: string | null
  phone: string | null
  branch_id: number
  course_id: number | null
  source: EnquirySource
  status: EnquiryStatus
  notes: string | null
  follow_up_date: string | null
  counsellor_id: number | null
  student_id: number | null
  converted_at: string | null
  created_at: string
  updated_at: string
}

export type EnquiryConversion = {
  enquiry: Enquiry
  student: { id: number; student_code: string; full_name: string }
  enrollment: { id: number; enrollment_code: string; status: string }
}

// Personalized Dashboard Types
export type ChartData = {
  type: 'line' | 'bar' | 'hbar' | 'donut'
  labels: string[]
  series: Array<{ name: string; data: number[] }>
  value_format: 'number' | 'currency' | 'percent'
}

export type DashboardCharts = Record<string, ChartData>

export type SuperAdminDashboardData = {
  dashboard_type: 'super_admin'
  total_branches: number
  active_branches: number
  total_students: number
  total_faculty: number
  total_staff: number
  monthly_revenue: number
  total_revenue: number
  total_outstanding: number
  overall_attendance_rate: number
  branches: Array<{
    id: number
    name: string
    code: string
    address: string | null
    phone: string | null
    email: string | null
    is_active: boolean
    admin_name: string
    students_count: number
    batches_count: number
    monthly_revenue: number
    attendance_rate: number
  }>
  recent_activities: Array<{
    id: number
    actor_name: string
    action: string
    resource_type: string
    resource_id: string
    created_at: string
  }>
  charts: DashboardCharts
}

export type BranchAdminDashboardData = {
  dashboard_type: 'branch_admin'
  branch_name: string
  branch_code: string
  branch_students_count: number
  branch_batches_count: number
  branch_faculty_count: number
  branch_staff_count: number
  monthly_collection: number
  outstanding_balance: number
  branch_attendance_rate: number
  staff_attendance_today: {
    present_today: number
    on_leave_today: number
    recorded_today: number
  }
  batches: Array<{
    id: number
    name: string
    code: string
    course_name: string
    faculty_name: string
    enrolled_count: number
    capacity: number
    start_date: string
    end_date: string | null
  }>
  overdue_installments: Array<{
    installment_id: number
    student_name: string
    student_phone: string
    amount: number
    due_date: string
    enrollment_code: string
  }>
  charts: DashboardCharts
}

export type FacultyDashboardData = {
  dashboard_type: 'faculty'
  faculty_name: string
  assigned_batches_count: number
  total_my_students: number
  batches_today_count: number
  attendance_marked_today_count: number
  attendance_rate: number
  my_attendance: {
    present: number
    absent: number
    late: number
    leave: number
    half_day: number
    recorded_days: number
    attendance_rate: number
  }
  my_batches: Array<{
    id: number
    name: string
    code: string
    course_name: string
    students_count: number
    capacity: number
    attendance_marked_today: boolean
    start_date: string
  }>
  recent_exams: Array<{
    id: number
    name: string
    batch_name: string
    exam_date: string
    is_published: boolean
    subjects_count: number
  }>
  charts: DashboardCharts
}

export type StaffDashboardData = {
  dashboard_type: 'staff'
  staff_name: string
  today_collection: number
  monthly_collection: number
  pending_installments_count: number
  total_pending_amount: number
  active_enrollments_count: number
  my_pending_responsibilities_count: number
  recent_payments: Array<{
    receipt_number: string
    student_name: string
    amount: number
    payment_method: string
    payment_date: string
  }>
  overdue_installments: Array<{
    installment_id: number
    student_name: string
    student_phone: string
    amount: number
    due_date: string
    enrollment_code: string
  }>
  my_responsibilities: Array<{
    id: number
    title: string
    department: string
    due_date: string | null
    status: string
  }>
  charts: DashboardCharts
}

export type CounsellorDashboardData = {
  dashboard_type: 'counsellor'
  counsellor_name: string
  branch_students_count: number
  admissions_this_month: number
  pending_followups_count: number
  open_enquiries_count: number
  followups_due_count: number
  conversions_this_month: number
  low_attendance_students_count: number
  academic_watchlist: Array<{
    student_id: number
    student_name: string
    student_code: string
    phone: string
    parent_name: string
    parent_phone: string
    batch_name: string
    attendance_rate: number
    total_classes: number
    attended_classes: number
  }>
  my_responsibilities: Array<{
    id: number
    title: string
    department: string
    due_date: string | null
    status: string
  }>
  charts: DashboardCharts
}

export type RoleDashboardData =
  | SuperAdminDashboardData
  | BranchAdminDashboardData
  | FacultyDashboardData
  | StaffDashboardData
  | CounsellorDashboardData
  | { dashboard_type: 'default' }

export type DashboardSummary = {
  role_name: string
  branch_id: number | null
  total_students: number
  active_courses: number
  active_batches: number
  fee_collection: number
  attendance_rate: number
  role_dashboard?: RoleDashboardData
}

export type ReportColumn = { key: string; label: string }
export type ReportSummaryItem = { label: string; value: string | number }
export type ReportCatalogEntry = {
  key: string
  title: string
  description: string
}
export type ReportResult = {
  key: string
  title: string
  description: string
  scope: string
  generated_at: string
  columns: ReportColumn[]
  rows: Array<Record<string, string | number>>
  summary: ReportSummaryItem[]
}
