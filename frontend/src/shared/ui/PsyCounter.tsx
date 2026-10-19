/** Счётчик психологических профилей занятия (F4, RF4-04): сколько состояний заявителя включено и в какой доле звонков. */
import { Tag } from '@smena112/ui-kit';
import { usePsyProfiles, type PsySettings } from '../api/training';

export function PsyCounter({ psy, detailed = false }: { psy?: PsySettings; detailed?: boolean }) {
  const all = usePsyProfiles().data ?? [];
  if (!psy?.enabled) return <span className="c-slate">{detailed ? 'выключен' : '—'}</span>;
  const share = `${Math.round(psy.share * 100)} % звонков`;
  if (psy.profiles === 'auto') {
    return <span><Tag variant="blue">профили: авто</Tag>{detailed && <> по сложности сценария · {share}</>}</span>;
  }
  const chosen = all.filter((p) => psy.profiles.includes(p.id));
  const names = chosen.map((p) => p.title).join(', ');
  return (
    <span title={names}>
      <Tag variant="blue">профилей: {psy.profiles.length}</Tag>
      {detailed && <> {names}{names && ' · '}{share}</>}
    </span>
  );
}
