/** Повторные обращения и связи карточек (п. 1.6, ТЗ 4.6) — как в АРМ-112:
 *  - баннер «Есть карточка с заявителем по этому номеру:» с «привязать» и «закрыть и продолжить заполнение новой» (`image62`);
 *  - «совпадение» по адресу — та же таблица (`image61`);
 *  - окно связей «Показ связей: карточек N» с «отвязать» и «вернуться в карточку» (`image65`).
 *  Строки — те же, что в «Списке происшествий». */
import { useMemo } from 'react';
import { useCardTypes } from '../../shared/api/dictionaries';
import { useCardLinks, useLinkCard, type JournalRow } from '../../shared/api/incidents';
import { JournalHead, Row, rowTitle } from '../journal/JournalPage';

/** Заголовок таблицы с местом под кнопку справа — колонки совпадают со строками. */
function Head() {
  return <div className="arm-links__row"><JournalHead /><span className="arm-links__act arm-links__act--gap" aria-hidden="true" /></div>;
}

function useTitles() {
  const cardTypes = useCardTypes();
  return useMemo(() => new Map((cardTypes.data ?? []).map((t) => [t.code, t.title])), [cardTypes.data]);
}

/** Совпадения при заполнении новой карточки: по номеру — открывается само, по адресу — кнопкой «совпадение». */
export function MatchesDialog({ cardId, rows, by, onClose }: { cardId: string; rows: JournalRow[]; by: 'phone' | 'address'; onClose: () => void }) {
  const titles = useTitles();
  const link = useLinkCard(cardId);
  const linked = link.data?.main_id ?? null;
  const isLinked = (r: JournalRow) => linked !== null && (linked === r.id || linked === r.main_card_id);
  return (
    <div className="arm-links" role="dialog" aria-modal="true" aria-label="Совпадение с карточками">
      <div className="arm-links__box">
        <div className="arm-links__head">{by === 'phone' ? 'Есть карточка с заявителем по этому номеру:' : 'Есть карточки по этому адресу:'}</div>
        <div className="arm-links__body">
          <Head />
          {rows.map((r) => (
            <div key={r.id} className="arm-links__row">
              <Row row={r} title={rowTitle(r, titles)} isNew={false} open={() => undefined} />
              <button type="button" className="arm-links__act" disabled={link.isPending || isLinked(r)}
                onClick={() => link.mutate(r.id, { onSuccess: onClose })}>
                {isLinked(r) ? 'привязана' : 'привязать'}
              </button>
            </div>
          ))}
        </div>
        {link.isError && <div className="arm-links__err" role="alert">{link.error.message}</div>}
        <div className="arm-links__foot arm-links__foot--center">
          <button type="button" className="arm-links__back" onClick={onClose}>закрыть и продолжить заполнение новой</button>
        </div>
      </div>
    </div>
  );
}

/** Окно связей карточки (кнопка со скрепкой в нижней панели). */
export function LinksDialog({ cardId, onClose }: { cardId: string; onClose: () => void }) {
  const titles = useTitles();
  const links = useCardLinks(cardId, true);
  const unlink = useLinkCard(cardId);
  const rows = links.data?.rows ?? [];
  const main = links.data?.main_id;
  return (
    <div className="arm-links" role="dialog" aria-modal="true" aria-label="Связи карточки">
      <div className="arm-links__box">
        <div className="arm-links__body">
          <Head />
          {links.isLoading && <div className="arm-empty">загрузка…</div>}
          {!links.isLoading && rows.length === 0 && (
            <div className="arm-empty">Связей нет. Привязать карточку к главной можно, когда совпадёт номер заявителя или адрес.</div>
          )}
          {rows.map((r) => (
            <div key={r.id} className="arm-links__row">
              <Row row={r} title={rowTitle(r, titles)} isNew={false} open={() => undefined} />
              {r.id === cardId && r.id !== main
                ? <button type="button" className="arm-links__act" disabled={unlink.isPending} onClick={() => unlink.mutate(null)}>отвязать</button>
                : <span className="arm-links__act arm-links__act--gap" aria-hidden="true" />}
            </div>
          ))}
        </div>
        {unlink.isError && <div className="arm-links__err" role="alert">{unlink.error.message}</div>}
        <div className="arm-links__foot">
          <button type="button" className="arm-links__back" onClick={onClose}>← вернуться в карточку</button>
          <span>Показ связей: карточек {rows.length}</span>
        </div>
      </div>
    </div>
  );
}
