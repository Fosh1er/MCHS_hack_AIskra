/** Опросная карта типа (Alt+1…9): дерево признаков классификатора 1 → 2 → 3 + вопросы-признаки Да/Нет,
 *  от которых зависят службы (колонки признаков в строке классификатора). Для 103 — «Отказ от реагирования Скорой». */
import { forwardRef } from 'react';
import { Chip, Icon } from '@smena112/ui-kit';
import type { EnumValue, Questionnaire } from '../../shared/api/dictionaries';
import { levels, type Action } from './state';
import { cardTypeLabel } from './WhatHappened';

export const LEVEL_TITLES = ['Признаки происшествия', 'Уточнение', 'Уточнение'];

export interface QuestionnaireProps {
  cardType: string;
  index: number;
  tree: Questionnaire | undefined;
  path: string[];
  flags: string[];
  flagAnswers: Record<string, boolean>;
  flagNames: Map<string, EnumValue>;
  refusal103: boolean;
  readOnly: boolean;
  dispatch: (a: Action) => void;
}

export const QuestionnairePanel = forwardRef<HTMLDivElement, QuestionnaireProps>(function QuestionnairePanel(
  { cardType, index, tree, path, flags, flagAnswers, flagNames, refusal103, readOnly, dispatch }, ref,
) {
  const title = tree ? cardTypeLabel(tree.card_type) : cardType;
  const rows = tree ? levels(tree.roots, path) : [];
  return (
    <section className="arm-q" ref={ref} tabIndex={-1} aria-label={`Опросная карта ${title}`}>
      <header className="arm-q__head">
        <span title={`Alt+${index + 1}`}>{title}</span>
        {!readOnly && <button type="button" aria-label={`Убрать тип ${title}`} onClick={() => dispatch({ type: 'removeType', code: cardType })}><Icon name="close" size="sm" /></button>}
      </header>
      {!tree && <div className="arm-q__note">Загрузка опросной карты…</div>}
      {tree && tree.roots.length === 0 && <div className="arm-q__note">Служебный тип: опросной карты и выезда служб нет.</div>}
      {rows.map((options, level) => (
        <div className="arm-q__row" key={level}>
          <span className="arm-q__label">{level === 0 ? LEVEL_TITLES[0] : `${LEVEL_TITLES[level]} (${path[level - 1]})`}</span>
          <span className="arm-chips arm-chips--tight">
            {options.map((n) => (
              <Chip key={n.label} selected={path[level] === n.label} onClick={readOnly ? undefined : () => dispatch({ type: 'choose', cardType, level, label: n.label })}>
                {n.label}
              </Chip>
            ))}
          </span>
        </div>
      ))}
      {flags.map((flag) => (
        <div className="arm-q__row" key={flag}>
          <span className="arm-q__label">{flagNames.get(flag)?.name ?? flag}</span>
          <span className="arm-chips arm-chips--tight">
            <Chip selected={flagAnswers[flag] === true} onClick={readOnly ? undefined : () => dispatch({ type: 'flagAnswer', flag, value: true })}>Да</Chip>
            <Chip selected={flagAnswers[flag] === false} onClick={readOnly ? undefined : () => dispatch({ type: 'flagAnswer', flag, value: false })}>Нет</Chip>
          </span>
        </div>
      ))}
      {cardType === '103' && (
        <div className="arm-q__row">
          <span className="arm-q__label">Отказ</span>
          <span><Chip selected={refusal103} onClick={readOnly ? undefined : () => dispatch({ type: 'refusal103' })}>Отказ от реагирования Скорой</Chip></span>
        </div>
      )}
    </section>
  );
});
