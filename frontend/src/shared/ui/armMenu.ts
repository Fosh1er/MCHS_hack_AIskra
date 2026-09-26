import { PERMISSIONS } from '../api/auth';
import type { MenuItem } from './ArmTopBar';

/** Меню АРМ-112 для обучающегося и преподавателя (шапка оригинала: журнал, экран, статистика…).
 *  Остальные разделы появятся с пунктами 4.x и 5.1. */
export const ARM_MENU: MenuItem[] = [
  { to: '/arm/112/journal', label: 'журнал 112', icon: 'table' },
  { to: '/arm/dds', label: 'АРМ ДДС', icon: 'headset' },
  { to: '/teacher', label: 'пульт преподавателя', icon: 'school', permission: PERMISSIONS.lessonsConduct },
];
