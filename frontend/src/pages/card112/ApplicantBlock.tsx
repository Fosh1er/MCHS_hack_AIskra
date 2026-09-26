/** Вторая полоса: заявитель (Alt+Q), канал связи (Alt+K); признаки пострадавших (Alt+P); «нет контакта» / «срыв звонка» (Alt+N). */
import { Icon } from '@smena112/ui-kit';
import type { EnumValue } from '../../shared/api/dictionaries';
import { type Action, type CardState } from './state';
import { Hint } from './Hint';

export function ApplicantRow({ state, dispatch, statuses, channels, readOnly }: {
  state: CardState; dispatch: (a: Action) => void; statuses: EnumValue[]; channels: EnumValue[]; readOnly: boolean;
}) {
  const a = state.applicant;
  return (
    <div className="arm-panel arm112-applicant arm112-rel">
      <Hint k="Alt+Q" />
      <label className="arm-field" style={{ flex: 1.4 }}>
        <span className="arm-field__label"> </span>
        <input
          id="applicant-name" className="arm-field__input" placeholder="Фамилия и имя заявителя" value={a.name} readOnly={readOnly}
          onChange={(e) => dispatch({ type: 'applicant', patch: { name: e.target.value.replace(/^\s*\S/, (c) => c.toUpperCase()) } })}
        />
      </label>
      <label className="arm-field" style={{ flex: 1 }}>
        <span className="arm-field__label"> </span>
        <select className="arm-uline arm-uline--select" aria-label="Статус заявителя" value={a.status} disabled={readOnly}
          onChange={(e) => dispatch({ type: 'applicant', patch: { status: e.target.value } })}>
          <option value="">выберите статус</option>
          {statuses.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
        </select>
      </label>
      <label className="arm-field arm112-rel" style={{ flex: 1 }}>
        <Hint k="Alt+K" />
        <span className="arm-field__label"> </span>
        <select id="channel" className="arm-uline arm-uline--select" aria-label="Канал связи" value={state.channel} disabled={readOnly}
          onChange={(e) => dispatch({ type: 'channel', value: e.target.value })}>
          <option value="">канал связи</option>
          {channels.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
        </select>
      </label>
      <button type="button" className="arm112-toggle" aria-pressed={a.foreign_language} disabled={readOnly}
        title="Вызов на иностранном языке" aria-label="Вызов на иностранном языке"
        onClick={() => dispatch({ type: 'applicant', patch: { foreign_language: !a.foreign_language } })}>
        <Icon name="translate" size="sm" />
      </button>
    </div>
  );
}

export function VictimsRow({ state, dispatch, readOnly, onEmpty }: {
  state: CardState; dispatch: (a: Action) => void; readOnly: boolean; onEmpty: (kind: 'no_contact' | 'call_dropped') => void;
}) {
  const f = state.topFlags;
  return (
    <div className="arm112__row2">
      <div className="arm-panel arm112-victims arm112-rel">
        <Hint k="Alt+P" />
        <button id="victims" type="button" className="arm-bigbtn" aria-pressed={f.victims} disabled={readOnly} onClick={() => dispatch({ type: 'topFlag', flag: 'victims' })}>Пострадавшие</button>
        <button type="button" className="arm-bigbtn" aria-pressed={f.notOnSite} disabled={readOnly} onClick={() => dispatch({ type: 'topFlag', flag: 'notOnSite' })}>Нет на месте/<br />Отказ от скорой</button>
        <button type="button" className="arm-bigbtn" aria-pressed={f.noAccess} disabled={readOnly} onClick={() => dispatch({ type: 'topFlag', flag: 'noAccess' })}>Нет доступа/<br />Заблокированные</button>
        {f.victims && (
          <label className="arm-field arm112-count" style={{ marginLeft: 8 }}>
            <span className="arm-field__label">Количество</span>
            <input className="arm-field__input" type="number" min={0} value={state.victimsCount || ''} readOnly={readOnly}
              onChange={(e) => dispatch({ type: 'victimsCount', value: Number(e.target.value) })} />
          </label>
        )}
      </div>
      <div className="arm-panel arm112-empty arm112-rel">
        <Hint k="Alt+N" />
        <button id="no-contact" type="button" className="arm-bigbtn arm-bigbtn--alert" disabled={readOnly} onClick={() => onEmpty('no_contact')}>нет контакта</button>
        <button type="button" className="arm-bigbtn arm-bigbtn--alert" disabled={readOnly} onClick={() => onEmpty('call_dropped')}>срыв звонка</button>
      </div>
    </div>
  );
}
