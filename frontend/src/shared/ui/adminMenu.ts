import { PERMISSIONS } from '../api/auth';
import type { MenuItem } from './ArmTopBar';

/** Меню администратора. Пользователи и настройки появятся в п. 5.2. */
export const ADMIN_MENU: MenuItem[] = [
  { to: '/admin/audit', label: 'аудит', icon: 'eye', permission: PERMISSIONS.auditRead },
  { to: '/dev/ai', label: 'ИИ-модели', icon: 'memory', permission: PERMISSIONS.systemManage },
];
