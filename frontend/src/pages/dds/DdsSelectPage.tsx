/** Вход в АРМ ДДС (п. 2.1). В реальном АРМ служба привязана к учётной записи (dds/image1), в тренажёре её задаёт
 *  занятие (4.2): диспетчеру на идущем занятии доступна только его служба (ТЗ 2.7, 2.8 — сервер отвечает 403 на
 *  чужую). Вне занятия — свободная практика: любая служба, только карточки вне занятий. Преподаватель — любая. */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PERMISSIONS, useMe } from '../../shared/api/auth';
import { useServices, type ServiceRow } from '../../shared/api/dictionaries';
import { useMySession } from '../../shared/api/training';
import { useScreenTour } from '../../shared/onboarding/OnboardingProvider';
import { ArmTopBar } from '../../shared/ui/ArmTopBar';
import { ARM_MENU } from '../../shared/ui/armMenu';

export const LAST_DDS_KEY = 'aiskra.dds.service';
const GROUPS: { title: string; kinds: string[] }[] = [
  { title: 'Экстренные службы', kinds: ['emergency', 'federal'] },
  { title: 'Городские службы и ведомства', kinds: ['city', 'department', 'utility', 'transport', 'government', 'okrug_roads', 'other'] },
  { title: 'Префектуры', kinds: ['prefecture_dds'] },
  { title: 'ДДС районов и поселений', kinds: ['district_dds'] },
];
const norm = (s: string) => s.toLowerCase().replace(/ё/g, 'е');

export function rememberDds(code: string) {
  try { localStorage.setItem(LAST_DDS_KEY, code); } catch { /* приватный режим — не запоминаем */ }
}
export function lastDds(): string | null {
  try { return localStorage.getItem(LAST_DDS_KEY); } catch { return null; }
}

export function DdsSelectPage() {
  const me = useMe().data!;
  const navigate = useNavigate();
  const services = useServices();
  useScreenTour('dds-select', !!services.data);
  const trainee = me.permissions.includes(PERMISSIONS.trainingParticipate);
  const my = useMySession(trainee);
  // диспетчер на идущем занятии — только своя служба; вне занятия (undefined) — любая, свободная практика
  const assigned = trainee && my.data?.role === 'dds' ? my.data.dds_service_code ?? undefined : undefined;
  const [q, setQ] = useState('');
  const last = assigned === undefined ? lastDds() : assigned;
  const filtered = useMemo(() => {
    const t = norm(q.trim());
    return (services.data ?? []).filter((s) => (assigned === undefined || s.code === assigned)
      && (!t || norm(`${s.short} ${s.full}`).includes(t)));
  }, [services.data, q, assigned]);
  const open = (s: ServiceRow) => { rememberDds(s.code); navigate(`/arm/dds/${encodeURIComponent(s.code)}`); };
  const lastRow = services.data?.find((s) => s.code === last);

  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <div className="arm-search__main">
          <input className="arm-search__input" autoFocus placeholder="Выберите службу (ДДС)" aria-label="Поиск службы" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && filtered[0]) open(filtered[0]); }} />
          <div className="arm-search__row">
            <span>За какую дежурно-диспетчерскую службу вы работаете на этом занятии</span>
            {lastRow && <button type="button" className="arm-newcard" onClick={() => open(lastRow)}>продолжить: {lastRow.short}</button>}
          </div>
        </div>
        <ArmTopBar me={me} menu={ARM_MENU} />
      </div>
      <div className="arm-list">
        {services.isError && <div className="arm-empty">Не удалось загрузить службы: {services.error.message}</div>}
        {trainee && my.isSuccess && !assigned && (
          <div className="arm-empty">Свободная практика: вы не диспетчер на идущем занятии — в журнале службы видны
            карточки, не привязанные к занятиям.</div>
        )}
        {GROUPS.map((g) => {
          const items = filtered.filter((s) => g.kinds.includes(s.kind));
          if (!items.length) return null;
          return (
            <section key={g.title} className="dds-pick">
              <div className="arm-list__title" style={{ marginBottom: 8 }}>{g.title}</div>
              <div className="dds-pick__grid">
                {items.map((s) => (
                  <button key={s.code} type="button" className="dds-pick__item" onClick={() => open(s)} title={s.full}>
                    <b>{s.short}</b><span>{s.full !== s.short ? s.full : ''}</span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
