/** Каркас кабинета преподавателя (ui-kit, preview/teacher-console.html): боковое меню, шапка, мобильная панель. */
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Sidebar, TabBar, Topbar, type NavItem } from '@smena112/ui-kit';
import { useLogout, useMe } from '../api/auth';

export type TeacherSection = 'home' | 'scenarios' | 'sessions' | 'journal' | 'dds';

const NAV: NavItem[] = [
  { id: 'home', label: 'Пульт', icon: 'dashboard', href: '/teacher', group: 'Преподаватель' },
  { id: 'scenarios', label: 'Банк сценариев', icon: 'library', href: '/teacher/scenarios' },
  { id: 'sessions', label: 'Занятия', icon: 'school', href: '/teacher/sessions' },
  { id: 'journal', label: 'Журнал 112', icon: 'table', href: '/arm/112/journal', group: 'АРМ' },
  { id: 'dds', label: 'АРМ ДДС', icon: 'headset', href: '/arm/dds' },
];

export const initials = (full: string) => full.split(/\s+/).slice(0, 2).map((p) => p[0] ?? '').join('').toUpperCase();

export function TeacherShell({ active, title, subtitle, crumbs, actions, children }: {
  active: TeacherSection; title: string; subtitle?: string; crumbs?: string; actions?: ReactNode; children: ReactNode;
}) {
  const me = useMe().data!;
  const navigate = useNavigate();
  const logout = useLogout();
  const go = (id: string) => { const it = NAV.find((n) => n.id === id); if (it?.href) navigate(it.href); };
  return (
    <AppShell
      sidebar={
        <Sidebar role="Преподаватель" items={NAV} activeId={active} onNavigate={go}
          user={{ name: me.full_name, sub: me.role_title, initials: initials(me.full_name) }}
          onLogout={() => logout.mutate(undefined, { onSettled: () => navigate('/', { replace: true }) })} />
      }
      topbar={<Topbar crumbs={crumbs} title={title} subtitle={subtitle} actions={actions} />}
      tabbar={<TabBar items={NAV.slice(0, 4)} activeId={active} onNavigate={go} />}
    >
      {children}
    </AppShell>
  );
}
