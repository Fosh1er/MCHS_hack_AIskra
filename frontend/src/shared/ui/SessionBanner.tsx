/** Баннер идущего занятия в АРМ обучающегося (п. 4.2): название, роль, куда идти. Роль ДДС — ссылка на свою службу. */
import { Link } from 'react-router-dom';
import { Icon } from '@smena112/ui-kit';
import { MODE_TITLE, type MySession } from '../api/training';

export function SessionBanner({ s, here, extra }: { s: MySession; here: '112' | 'dds'; extra?: string }) {
  const role = s.role === '112' ? 'оператор 112' : `диспетчер ДДС ${s.dds_service_code}`;
  return (
    <div className="session-banner" role="status">
      <Icon name="school" size="sm" />
      <span>
        Идёт занятие <b>«{s.title}»</b> · {MODE_TITLE[s.mode]} · ваша роль — <b>{role}</b>
        {extra ? ` · ${extra}` : ''}
      </span>
      {s.role === 'dds' && here === '112' && s.dds_service_code && (
        <Link className="session-banner__go" to={`/arm/dds/${encodeURIComponent(s.dds_service_code)}`}>перейти в АРМ ДДС</Link>
      )}
      {s.role === '112' && here === 'dds' && <Link className="session-banner__go" to="/arm/112/journal">перейти в журнал 112</Link>}
    </div>
  );
}
