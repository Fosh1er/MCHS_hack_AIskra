import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { AiDiagnosticsPage } from '../pages/AiDiagnosticsPage';
import { AuditPage } from '../pages/admin/AuditPage';
import { RoleHomePage } from '../pages/RoleHomePage';
import { Card112NewPage, Card112Page } from '../pages/card112/Card112Page';
import { JournalPage } from '../pages/journal/JournalPage';
import { DdsCardPage } from '../pages/dds/DdsCardPage';
import { DdsJournalPage } from '../pages/dds/DdsJournalPage';
import { DdsSelectPage } from '../pages/dds/DdsSelectPage';
import { ScenariosPage } from '../pages/teacher/ScenariosPage';
import { SessionsPage } from '../pages/teacher/SessionsPage';
import { SessionMonitorPage } from '../pages/teacher/SessionMonitorPage';
import { SessionReportPage } from '../pages/teacher/SessionReportPage';
import { ProgressPage } from '../pages/student/ProgressPage';
import { PERMISSIONS } from '../shared/api/auth';
import { RequireAuth } from '../shared/auth/RequireAuth';

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/admin/audit', element: <RequireAuth permission={PERMISSIONS.auditRead}><AuditPage /></RequireAuth> },
  { path: '/dev/ai', element: <RequireAuth permission={PERMISSIONS.systemManage}><AiDiagnosticsPage /></RequireAuth> },
  { path: '/teacher', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><RoleHomePage /></RequireAuth> },
  { path: '/teacher/scenarios', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><ScenariosPage /></RequireAuth> },
  { path: '/teacher/sessions', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionsPage /></RequireAuth> },
  { path: '/teacher/sessions/:id', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionMonitorPage /></RequireAuth> },
  { path: '/teacher/sessions/:id/report', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionReportPage /></RequireAuth> },
  { path: '/student/progress', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><ProgressPage /></RequireAuth> },
  { path: '/student', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><RoleHomePage /></RequireAuth> },
  // журнал: свои карточки — обучающемуся, все — преподавателю (сервер, п. 1.3)
  { path: '/arm/112/journal', element: <RequireAuth><JournalPage /></RequireAuth> },
  { path: '/arm/112', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><Card112NewPage /></RequireAuth> },
  // своя карточка — обучающемуся, любая — преподавателю: права проверяет сервер (GET /incidents/cards/{id})
  { path: '/arm/112/:id', element: <RequireAuth><Card112Page /></RequireAuth> },
  // АРМ ДДС (п. 2.1, 2.2): обучающийся работает за выбранную службу, преподаватель смотрит; права — на сервере
  { path: '/arm/dds', element: <RequireAuth><DdsSelectPage /></RequireAuth> },
  { path: '/arm/dds/:service', element: <RequireAuth><DdsJournalPage /></RequireAuth> },
  { path: '/arm/dds/:service/:id', element: <RequireAuth><DdsCardPage /></RequireAuth> },
  { path: '*', element: <Navigate to="/" replace /> },
]);
