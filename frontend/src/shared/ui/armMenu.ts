import { PERMISSIONS } from '../api/auth';
import type { MenuItem } from './ArmTopBar';

/** Меню АРМ-112 для обучающегося и преподавателя (шапка оригинала: журнал, экран, статистика…).
 *  Банк сценариев и занятия — в кабинете преподавателя (/teacher). */
export const ARM_MENU: MenuItem[] = [
  { to: '/arm/112/journal', label: 'журнал 112', icon: 'table' },
  { to: '/arm/dds', label: 'АРМ ДДС', icon: 'headset' },
  { to: '/student', label: 'кабинет', icon: 'person', permission: PERMISSIONS.trainingParticipate },
  { to: '/teacher', label: 'пульт преподавателя', icon: 'school', permission: PERMISSIONS.lessonsConduct },
];
