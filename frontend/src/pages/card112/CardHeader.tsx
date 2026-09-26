/** Верхняя полоса: управление вызовом, три телефона, номер карточки, таймер (стенд 2026, image1). */
import { CallControl, CardTimer, Icon } from '@smena112/ui-kit';
import { CARD_NORM_SECONDS, formatPhone, type Action, type CardState } from './state';
import { Hint } from './Hint';

interface PhoneProps {
  id: string;
  label: string;
  value: string;
  hint: string;
  readOnly?: boolean;
  foreign: boolean;
  onChange?: (v: string) => void;
  onCopyAon?: () => void;
  onForeign?: () => void;
  aonTools?: boolean;
}

function PhoneInput({ id, label, value, hint, readOnly, foreign, onChange, onCopyAon, onForeign, aonTools }: PhoneProps) {
  return (
    <div className="arm-phone arm112-rel">
      <Hint k={hint} style={{ left: 34 }} />
      <div className="arm-phone__icons">
        <button type="button" aria-label={`Позвонить: ${label}`} disabled title="Исходящий звонок — п. 1.4"><Icon name="phone" size="sm" /></button>
        <button type="button" aria-label={`SMS: ${label}`} disabled title="СМС заявителю — п. 1.4"><Icon name="sms" size="sm" /></button>
      </div>
      <div className="arm-phone__field">
        <div className="arm-phone__head">
          <label className="arm-phone__label" htmlFor={id}>{label}</label>
          <span className="arm-phone__tools">
            {aonTools && <button type="button" disabled title="Запрос данных абонента — п. 1.4" aria-label="Данные абонента"><Icon name="help" size="xs" /></button>}
            {aonTools && <button type="button" disabled title="Местоположение абонента от оператора связи — п. 1.4" aria-label="Местоположение"><Icon name="place" size="xs" /></button>}
            <button type="button" aria-pressed={foreign} onClick={onForeign} disabled={!onForeign} title="Зарубежный номер" aria-label="Зарубежный номер"><Icon name="translate" size="xs" /></button>
          </span>
        </div>
        <div className="arm-phone__row">
          <input
            id={id}
            className="arm-phone__input"
            value={value}
            readOnly={readOnly}
            placeholder={readOnly ? 'нет номера' : '+7 (   )    -  -'}
            inputMode="tel"
            onChange={(e) => onChange?.(foreign ? e.target.value : formatPhone(e.target.value))}
          />
          {onCopyAon && <button type="button" className="arm-aonbtn" onClick={onCopyAon} title="Скопировать номер АОН">АОН</button>}
        </div>
      </div>
    </div>
  );
}

export interface HeaderInfo {
  number: number | null;
  registeredAt: Date | null;
  savedAt: Date | null;
  operator: string;
}

export function CardHeader({ state, dispatch, info, seconds, readOnly }: {
  state: CardState; dispatch: (a: Action) => void; info: HeaderInfo; seconds: number; readOnly: boolean;
}) {
  const fmt = (d: Date) => `${d.toLocaleDateString('ru-RU')} в ${d.toLocaleTimeString('ru-RU')}`;
  const copyAon = (field: 'provided' | 'on_site') => () => dispatch({ type: 'phone', field, value: state.phones.aon });
  return (
    <div className="arm112__top">
      <CallControl title="Отключение" recordsDisabled />
      <PhoneInput id="phone-aon" label="АОН" hint="Alt+F1" value={state.phones.aon} readOnly foreign={state.phones.foreign} aonTools />
      <PhoneInput
        id="phone-provided" label="предоставленный" hint="Alt+F2" value={state.phones.provided} readOnly={readOnly} foreign={state.phones.foreign}
        onChange={(v) => dispatch({ type: 'phone', field: 'provided', value: v })}
        onCopyAon={readOnly ? undefined : copyAon('provided')}
        onForeign={readOnly ? undefined : () => dispatch({ type: 'foreign', value: !state.phones.foreign })}
      />
      <PhoneInput
        id="phone-on-site" label="телефон на место" hint="Alt+F3" value={state.phones.on_site} readOnly={readOnly} foreign={state.phones.foreign}
        onChange={(v) => dispatch({ type: 'phone', field: 'on_site', value: v })}
        onCopyAon={readOnly ? undefined : copyAon('on_site')}
        onForeign={readOnly ? undefined : () => dispatch({ type: 'foreign', value: !state.phones.foreign })}
      />
      <div className="arm-idbox" style={{ width: 235 }}>
        <div className="arm-idbox__title">Происшествие {info.number ?? '…'}</div>
        <div className="arm-idbox__meta">
          {info.savedAt ? `Сохр. ${fmt(info.savedAt)}` : info.registeredAt ? `Зарег. ${fmt(info.registeredAt)}` : ' '}
          <br />Опер. {info.operator}
        </div>
      </div>
      <CardTimer seconds={seconds} normSeconds={CARD_NORM_SECONDS} />
    </div>
  );
}
