import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { AiDiagnosticsPage } from '../pages/AiDiagnosticsPage';
import { AuditPage } from '../pages/admin/AuditPage';
import { RoleHomePage } from '../pages/RoleHomePage';
import { PERMISSIONS } from '../shared/api/auth';
import { RequireAuth } from '../shared/auth/RequireAuth';

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/admin/audit', element: <RequireAuth permission={PERMISSIONS.auditRead}><AuditPage /></RequireAuth> },
  { path: '/dev/ai', element: <RequireAuth permission={PERMISSIONS.systemManage}><AiDiagnosticsPage /></RequireAuth> },
  { path: '/teacher', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><RoleHomePage /></RequireAuth> },
  { path: '/student', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><RoleHomePage /></RequireAuth> },
  { path: '*', element: <Navigate to="/" replace /> },
]);
