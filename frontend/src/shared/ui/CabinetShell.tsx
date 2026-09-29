/** Каркас кабинетов (ui-kit, preview/*.html): боковое меню роли, шапка, мобильная панель. Преподаватель,
 *  администратор и обучающийся — одна стилистика, разные разделы. */
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell, Sidebar, TabBar, Topbar, type NavItem } from '@smena112/ui-kit';
import { useLogout, useMe } from '../api/auth';
import { useAlerts } from '../api/admin';
import { TourCabinetButton } from '../onboarding/OnboardingProvider';

/** Голосовой полигон (п. 3.6) — статическая страница `public/voice-lab/`, вне маршрутов SPA. */
const VOICE_LAB = '/voice-lab/index.html';

export const NAV: Record<'teacher' | 'admin' | 'student', { role: string; items: NavItem[] }> = {
  teacher: {
    role: 'Преподаватель',
    items: [
      { id: 'home', label: 'Пульт', icon: 'dashboard', href: '/teacher', group: 'Преподаватель' },
      { id: 'scenarios', label: 'Банк сценариев', icon: 'library', href: '/teacher/scenarios' },
      { id: 'sessions', label: 'Занятия', icon: 'school', href: '/teacher/sessions' },
      { id: 'analytics', label: 'Аналитика', icon: 'bar_chart', href: '/teacher/analytics' },
      { id: 'readiness', label: 'Допуск', icon: 'check_circle', href: '/teacher/readiness' },
      { id: 'validation', label: 'Достоверность', icon: 'shield', href: '/teacher/validation' },
      { id: 'materials', label: 'Учебные материалы', icon: 'description', href: '/teacher/materials' },
      { id: 'journal', label: 'Журнал 112', icon: 'table', href: '/arm/112/journal', group: 'АРМ' },
      { id: 'dds', label: 'АРМ ДДС', icon: 'headset', href: '/arm/dds' },
      { id: 'voice', label: 'Голосовой полигон', icon: 'headset', href: VOICE_LAB },
    ],
  },
  admin: {
    role: 'Администратор',
    items: [
      { id: 'status', label: 'Состояние', icon: 'dashboard', href: '/admin', group: 'Администратор' },
      { id: 'users', label: 'Пользователи', icon: 'person', href: '/admin/users' },
      { id: 'groups', label: 'Группы', icon: 'group', href: '/admin/groups' },
      { id: 'settings', label: 'Настройки и копии', icon: 'settings', href: '/admin/settings' },
      { id: 'materials', label: 'Учебные материалы', icon: 'library', href: '/teacher/materials' },
      { id: 'audit', label: 'Аудит', icon: 'eye', href: '/admin/audit', group: 'Журналы' },
      { id: 'logs', label: 'Логи', icon: 'description', href: '/admin/logs' },
      { id: 'ai', label: 'ИИ-модели', icon: 'memory', href: '/dev/ai' },
    ],
  },
  student: {
    role: 'Обучающийся',
    items: [
      { id: 'home', label: 'Кабинет', icon: 'dashboard', href: '/student', group: 'Обучающийся' },
      { id: 'progress', label: 'Мои результаты', icon: 'bar_chart', href: '/student/progress' },
      { id: 'reference', label: 'Справочная база', icon: 'library', href: '/student/reference' },
      { id: 'journal', label: 'АРМ-112', icon: 'table', href: '/arm/112/journal', group: 'Эмулятор' },
      { id: 'dds', label: 'АРМ ДДС', icon: 'headset', href: '/arm/dds' },
      { id: 'voice', label: 'Голосовой полигон', icon: 'headset', href: VOICE_LAB },
    ],
  },
};

export const initials = (full: string) => full.split(/\s+/).slice(0, 2).map((p) => p[0] ?? '').join('').toUpperCase();

export function CabinetShell({ kind, active, title, subtitle, crumbs, actions, children }: {
  kind: keyof typeof NAV; active: string; title: string; subtitle?: string; crumbs?: string; actions?: ReactNode; children: ReactNode;
}) {
  const me = useMe().data!;
  const navigate = useNavigate();
  const logout = useLogout();
  // п. 10.6: у администратора — счётчик оповещений о сбоях на пункте «Состояние»
  const alerts = useAlerts(kind === 'admin').data ?? [];
  const nav = kind === 'admin' && alerts.length
    ? { ...NAV.admin, items: NAV.admin.items.map((n) => (n.id === 'status' ? { ...n, count: alerts.length, alert: alerts.some((a) => a.level === 'critical') } : n)) }
    : NAV[kind];
  const go = (id: string) => { const it = nav.items.find((n) => n.id === id); if (it?.href === VOICE_LAB) window.location.assign(VOICE_LAB); else if (it?.href) navigate(it.href); };
  return (
    <AppShell
      sidebar={
        <Sidebar role={nav.role} items={nav.items} activeId={active} onNavigate={go}
          user={{ name: me.full_name, sub: me.role_title, initials: initials(me.full_name) }}
          onLogout={() => logout.mutate(undefined, { onSettled: () => navigate('/', { replace: true }) })} />
      }
      topbar={<Topbar crumbs={crumbs} title={title} subtitle={subtitle}
        actions={kind === 'teacher' ? <>{actions}<TourCabinetButton /></> : actions} />}
      tabbar={<TabBar items={nav.items} activeId={active} onNavigate={go} />}
    >
      {children}
    </AppShell>
  );
}
