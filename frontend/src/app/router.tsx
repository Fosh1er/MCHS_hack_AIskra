import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { AiDiagnosticsPage } from '../pages/AiDiagnosticsPage';
import { AuditPage } from '../pages/admin/AuditPage';
import { RoleHomePage } from '../pages/RoleHomePage';
import { Card112NewPage, Card112Page } from '../pages/card112/Card112Page';
import { JournalPage } from '../pages/journal/JournalPage';
import { PERMISSIONS } from '../shared/api/auth';
import { RequireAuth } from '../shared/auth/RequireAuth';

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/admin/audit', element: <RequireAuth permission={PERMISSIONS.auditRead}><AuditPage /></RequireAuth> },
  { path: '/dev/ai', element: <RequireAuth permission={PERMISSIONS.systemManage}><AiDiagnosticsPage /></RequireAuth> },
  { path: '/teacher', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><RoleHomePage /></RequireAuth> },
  { path: '/student', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><RoleHomePage /></RequireAuth> },
  // журнал: свои карточки — обучающемуся, все — преподавателю (сервер, п. 1.3)
  { path: '/arm/112/journal', element: <RequireAuth><JournalPage /></RequireAuth> },
  { path: '/arm/112', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><Card112NewPage /></RequireAuth> },
  // своя карточка — обучающемуся, любая — преподавателю: права проверяет сервер (GET /incidents/cards/{id})
  { path: '/arm/112/:id', element: <RequireAuth><Card112Page /></RequireAuth> },
  { path: '*', element: <Navigate to="/" replace /> },
]);
