/** Стартовые разделы преподавателя и обучающегося. Наполнение — пункты 4.x (преподаватель) и 1.x, 5.1 (обучающийся). */
import { useMe } from '../shared/api/auth';
import { ArmTopBar } from '../shared/ui/ArmTopBar';

const NEXT: Record<string, string> = {
  teacher: 'Пульт преподавателя: сценарии, занятия, мониторинг и оценки — пункты 3.x и 4.x плана.',
  student: 'Кабинет обучающегося: назначенные занятия и эмулятор АРМ-112 / ДДС — пункты 1.x, 2.x и 5.1 плана.',
};

export function RoleHomePage() {
  const me = useMe().data!;
  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <div className="arm-search__main">
          <h1 className="cab-title" style={{ margin: 0 }}>{me.role_title}</h1>
          <p style={{ marginTop: 8 }}>{NEXT[me.role]}</p>
        </div>
        <ArmTopBar me={me} menu={[]} />
      </div>
    </div>
  );
}
