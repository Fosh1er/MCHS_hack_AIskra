/** Правая часть шапки АРМ (image114): дата, пользователь, «обучение» (п. 5.3), «выйти», часы; ниже — меню разделов. */
import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '@smena112/ui-kit';
import { useLogout, type Me } from '../api/auth';
import { useTourControls } from '../onboarding/OnboardingProvider';

export interface MenuItem { to: string; label: string; icon: IconName; permission?: string }

const WEEKDAYS = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const pad = (n: number) => String(n).padStart(2, '0');

/** «Петров Пётр Петрович» → «Петров П П», как в шапке оригинала. */
export function shortName(full: string): string {
  const [last, ...rest] = full.split(/\s+/);
  return [last, ...rest.map((p) => p[0])].join(' ');
}

function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function ArmTopBar({ me, menu }: { me: Me; menu: MenuItem[] }) {
  const now = useNow();
  const logout = useLogout();
  const tour = useTourControls();
  const navigate = useNavigate();
  const items = menu.filter((m) => !m.permission || me.permissions.includes(m.permission));
  const onLogout = () => logout.mutate(undefined, { onSettled: () => navigate('/', { replace: true }) });

  return (
    <div>
      <div className="arm-clockpanel">
        <div>
          <div className="arm-clockpanel__date">
            {WEEKDAYS[now.getDay()]}, {now.getDate()} {MONTHS[now.getMonth()]} {now.getFullYear()}
          </div>
          <div className="arm-clockpanel__user">
            <span>{shortName(me.full_name)}{me.arm_number ? ` · АРМ ${me.arm_number}` : ''}</span>
            {tour.available && (
              <button type="button" data-tour="help" onClick={tour.replay} title="Подсказки по кнопкам этого экрана">
                <Icon name="help" size="xs" /> обучение
              </button>
            )}
            <button type="button" onClick={onLogout} disabled={logout.isPending}>
              <Icon name="logout" size="xs" /> выйти
            </button>
          </div>
        </div>
        <div className="arm-clockpanel__time" aria-label="Текущее время">
          {pad(now.getHours())}:{pad(now.getMinutes())}<span className="t-sec">:{pad(now.getSeconds())}</span>
        </div>
      </div>
      <nav className="arm-menu" aria-label="Разделы">
        {items.map((m) => (
          <NavLink key={m.to} to={m.to} className={({ isActive }) => `arm-menu__item${isActive ? ' arm-menu__item--active' : ''}`}>
            <Icon name={m.icon} size="sm" />
            {m.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
