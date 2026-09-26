/** Каркас кабинета преподавателя — `CabinetShell` с разделами преподавателя. */
import type { ReactNode } from 'react';
import { CabinetShell } from './CabinetShell';

export { initials } from './CabinetShell';
export type TeacherSection = 'home' | 'scenarios' | 'sessions' | 'journal' | 'dds';

export function TeacherShell(p: {
  active: TeacherSection; title: string; subtitle?: string; crumbs?: string; actions?: ReactNode; children: ReactNode;
}) {
  return <CabinetShell kind="teacher" {...p} />;
}
