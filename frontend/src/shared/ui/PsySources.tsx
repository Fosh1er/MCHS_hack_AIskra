/** Ссылки на источники методики психологического модификатора (F4): код реестра → подпись и ссылка на первоисточник.
 *  Реестр отдаёт сервер (`GET /training/psy/methodology`, данные — `psy_profiles.yaml`), во фронте текста нет. */
import { Fragment } from 'react';
import type { Cite } from '../api/assessment';
import { PERMISSIONS, useMe } from '../api/auth';
import { usePsyMethodology, type PsySource } from '../api/training';

export function useSourceRegistry(): Record<string, PsySource> {
  return usePsyMethodology().data?.sources ?? {};
}

/** Где открыть страницу «Методика»: у преподавателя — его раздел, у остальных — вкладка справочной базы. */
export function useMethodologyHref(): string {
  const me = useMe().data;
  return me?.permissions.includes(PERMISSIONS.lessonsConduct) ? '/teacher/methodology' : '/student/reference?tab=methodology';
}

export function SourceRefs({ cites, codes, label = 'Источник' }: { cites?: Cite[]; codes?: string[]; label?: string }) {
  const reg = useSourceRegistry();
  const list = cites ?? (codes ?? []).map((source) => ({ source, at: '' }));
  if (!list.length) return null;
  return (
    <span className="psy-src">
      {label && <>{label}: </>}
      {list.map((c, i) => {
        const s = reg[c.source];
        const text = s?.short ?? c.source;
        return (
          <Fragment key={`${c.source}-${c.at}`}>
            {i > 0 && '; '}
            {s?.url
              ? <a href={s.url} target="_blank" rel="noreferrer" title={s.title}>{text}</a>
              : <span title={s?.title}>{text}</span>}
            {c.at && ` (${c.at})`}
          </Fragment>
        );
      })}
    </span>
  );
}
