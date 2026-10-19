/** «Методика» в кабинете преподавателя (F4, RF4-03): на чём построен психологический модификатор. */
import { TeacherShell } from '../../shared/ui/TeacherShell';
import { PsyMethodologyView } from '../../shared/ui/PsyMethodology';

export function MethodologyPage() {
  return (
    <TeacherShell active="methodology" crumbs="Пульт / Методика" title="Методика"
      subtitle="Заявитель в стрессе: состояния, действия оператора, источники">
      <PsyMethodologyView />
    </TeacherShell>
  );
}
