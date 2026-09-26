import { PERMISSIONS } from '../api/auth';
import type { MenuItem } from './ArmTopBar';

/** Меню администратора в разделах АРМ-стиля (аудит). Остальное — в кабинете администратора (/admin). */
export const ADMIN_MENU: MenuItem[] = [
  { to: '/admin', label: 'панель', icon: 'dashboard', permission: PERMISSIONS.systemManage },
  { to: '/admin/audit', label: 'аудит', icon: 'eye', permission: PERMISSIONS.auditRead },
  { to: '/dev/ai', label: 'ИИ-модели', icon: 'memory', permission: PERMISSIONS.systemManage },
];
