/** Стартовые разделы преподавателя и обучающегося. Наполнение — пункты 4.x (преподаватель) и 1.x, 5.1 (обучающийся). */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PERMISSIONS, useMe } from '../shared/api/auth';
import { keyCode } from './card112/useHotkeys';
import { ArmTopBar } from '../shared/ui/ArmTopBar';

const NEXT: Record<string, string> = {
  teacher: 'Пульт преподавателя: сценарии, занятия, мониторинг и оценки — пункты 3.x и 4.x плана.',
  student: 'Кабинет обучающегося: назначенные занятия и эмулятор АРМ-112 / ДДС — пункты 1.x, 2.x и 5.1 плана.',
};

export function RoleHomePage() {
  const me = useMe().data!;
  const navigate = useNavigate();
  const canCreate = me.permissions.includes(PERMISSIONS.trainingParticipate);
  useEffect(() => {
    if (!canCreate) return;
    const onKey = (e: KeyboardEvent) => { if (keyCode(e) === 'Insert') navigate('/arm/112'); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canCreate, navigate]);
  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <div className="arm-search__main">
          <h1 className="cab-title" style={{ margin: 0 }}>{me.role_title}</h1>
          <p style={{ marginTop: 8 }}>{NEXT[me.role]}</p>
          {canCreate && (
            <button type="button" className="arm-bigbtn arm-bigbtn--alert" style={{ marginTop: 12 }} onClick={() => navigate('/arm/112')}>
              создать новую карточку (Insert)
            </button>
          )}
        </div>
        <ArmTopBar me={me} menu={[]} />
      </div>
    </div>
  );
}
