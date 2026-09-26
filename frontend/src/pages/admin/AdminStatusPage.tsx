/** Состояние сервисов (п. 5.2, ТЗ: health-checks БД, ИИ-провайдера, телефонии) и импорт справочников. */
import { Fragment } from 'react';
import { Banner, Button, Card, ServiceHealth, type IconName } from '@smena112/ui-kit';
import { useImport, useStatus } from '../../shared/api/admin';
import { CabinetShell } from '../../shared/ui/CabinetShell';

const icon = (name: string): IconName =>
  name.startsWith('ИИ') ? 'memory' : name === 'База данных' ? 'storage' : name === 'Телефония' ? 'phone' : name === 'Кеш ИИ' ? 'bolt' : 'save';

function ImportCard() {
  const imp = useImport();
  const r = imp.data;
  return (
    <Card title="Импорт справочников" subtitle="Из каталога data/: классификатор, службы, территория, перечисления; адреса и границы районов">
      <div className="cab-filters">
        <Button icon="refresh" disabled={imp.isPending} onClick={() => imp.mutate('dictionaries')}>классификатор и справочники</Button>
        <Button icon="place" disabled={imp.isPending} onClick={() => imp.mutate('addresses')}>адреса и районы</Button>
        {imp.isPending && <span className="cab-filters__label">импорт…</span>}
      </div>
      {imp.isError && <Banner status="critical">{imp.error.message}</Banner>}
      {r && (
        <dl className="tch-dl" style={{ marginTop: 10 }}>
          <dt>Файл</dt><dd>{r.source_file.split('/').pop()}</dd>
          {Object.entries(r.counts).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
          {r.warnings.length > 0 && <><dt>Предупреждения</dt><dd>{r.warnings.slice(0, 5).join('; ')}{r.warnings.length > 5 ? ` и ещё ${r.warnings.length - 5}` : ''}</dd></>}
        </dl>
      )}
    </Card>
  );
}

export function AdminStatusPage() {
  const q = useStatus();
  const bad = q.data?.filter((s) => s.state === 'critical') ?? [];
  return (
    <CabinetShell kind="admin" active="status" title="Состояние системы" subtitle="обновляется каждые 15 с">
      {q.isError && <Banner status="critical">Бэкенд недоступен: {q.error.message}</Banner>}
      {bad.length > 0 && <Banner status="critical">Неисправно: {bad.map((s) => s.name).join(', ')}</Banner>}
      <section className="cab-svcs">
        {q.data?.map((s) => (
          <div key={s.name}>
            <ServiceHealth name={s.name} icon={icon(s.name)} state={s.state} metrics={s.metrics} />
            {s.note && <p className="adm-note">{s.note}</p>}
          </div>
        ))}
      </section>
      <ImportCard />
    </CabinetShell>
  );
}
