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
import { MaterialsPage } from '../pages/teacher/MaterialsPage';
import { SessionsPage } from '../pages/teacher/SessionsPage';
import { SessionMonitorPage } from '../pages/teacher/SessionMonitorPage';
import { SessionReportPage } from '../pages/teacher/SessionReportPage';
import { ProgressPage } from '../pages/student/ProgressPage';
import { StudentHomePage } from '../pages/student/StudentHomePage';
import { MySessionPage } from '../pages/student/MySessionPage';
import { ReferencePage } from '../pages/student/ReferencePage';
import { AdminStatusPage } from '../pages/admin/AdminStatusPage';
import { UsersPage } from '../pages/admin/UsersPage';
import { GroupsPage } from '../pages/admin/GroupsPage';
import { SettingsPage } from '../pages/admin/SettingsPage';
import { LogsPage } from '../pages/admin/LogsPage';
import { PERMISSIONS } from '../shared/api/auth';
import { RequireAuth } from '../shared/auth/RequireAuth';
import { ArmScreenGuard } from '../shared/ui/ArmScreenGuard';

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/admin', element: <RequireAuth permission={PERMISSIONS.systemManage}><AdminStatusPage /></RequireAuth> },
  { path: '/admin/users', element: <RequireAuth permission={PERMISSIONS.usersManage}><UsersPage /></RequireAuth> },
  { path: '/admin/groups', element: <RequireAuth permission={PERMISSIONS.usersManage}><GroupsPage /></RequireAuth> },
  { path: '/admin/settings', element: <RequireAuth permission={PERMISSIONS.systemManage}><SettingsPage /></RequireAuth> },
  { path: '/admin/logs', element: <RequireAuth permission={PERMISSIONS.systemManage}><LogsPage /></RequireAuth> },
  { path: '/admin/audit', element: <RequireAuth permission={PERMISSIONS.auditRead}><AuditPage /></RequireAuth> },
  { path: '/dev/ai', element: <RequireAuth permission={PERMISSIONS.systemManage}><AiDiagnosticsPage /></RequireAuth> },
  { path: '/teacher', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><RoleHomePage /></RequireAuth> },
  { path: '/teacher/scenarios', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><ScenariosPage /></RequireAuth> },
  { path: '/teacher/materials', element: <RequireAuth anyOf={[PERMISSIONS.scenariosManage, PERMISSIONS.systemManage]}><MaterialsPage /></RequireAuth> },
  { path: '/teacher/sessions', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionsPage /></RequireAuth> },
  { path: '/teacher/sessions/:id', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionMonitorPage /></RequireAuth> },
  { path: '/teacher/sessions/:id/report', element: <RequireAuth permission={PERMISSIONS.lessonsConduct}><SessionReportPage /></RequireAuth> },
  { path: '/student/progress', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><ProgressPage /></RequireAuth> },
  { path: '/student', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><StudentHomePage /></RequireAuth> },
  { path: '/student/sessions/:id', element: <RequireAuth permission={PERMISSIONS.trainingParticipate}><MySessionPage /></RequireAuth> },
  { path: '/student/reference', element: <RequireAuth><ReferencePage /></RequireAuth> },
  // журнал: свои карточки — обучающемуся, все — преподавателю (сервер, п. 1.3)
  { path: '/arm/112/journal', element: <ArmScreenGuard><RequireAuth><JournalPage /></RequireAuth></ArmScreenGuard> },
  { path: '/arm/112', element: <ArmScreenGuard><RequireAuth permission={PERMISSIONS.trainingParticipate}><Card112NewPage /></RequireAuth></ArmScreenGuard> },
  // своя карточка — обучающемуся, любая — преподавателю: права проверяет сервер (GET /incidents/cards/{id})
  { path: '/arm/112/:id', element: <ArmScreenGuard><RequireAuth><Card112Page /></RequireAuth></ArmScreenGuard> },
  // АРМ ДДС (п. 2.1, 2.2): обучающийся работает за выбранную службу, преподаватель смотрит; права — на сервере
  { path: '/arm/dds', element: <ArmScreenGuard><RequireAuth><DdsSelectPage /></RequireAuth></ArmScreenGuard> },
  { path: '/arm/dds/:service', element: <ArmScreenGuard><RequireAuth><DdsJournalPage /></RequireAuth></ArmScreenGuard> },
  { path: '/arm/dds/:service/:id', element: <ArmScreenGuard><RequireAuth><DdsCardPage /></RequireAuth></ArmScreenGuard> },
  { path: '*', element: <Navigate to="/" replace /> },
]);
