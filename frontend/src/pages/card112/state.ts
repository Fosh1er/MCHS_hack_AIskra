/** Состояние карточки 112 (п. 1.1): чистый редьюсер + производные значения. Без React — легко проверять. */
import type { CardAddress, CardData, CardServiceIn } from '../../shared/api/incidents';
import type { ResolvedService, TreeNode } from '../../shared/api/dictionaries';

export const DESCRIPTION_MAX = 1999;
export const AMBULANCE_VISIBLE_CHARS = 100;
/** Норматив таймера. На стенде 01:03 — тёмный, 01:23 — красный; точное значение уточняется у заказчика. */
export const CARD_NORM_SECONDS = 80;

/** Три кнопки стенда 2026 под шапкой = признаки маршрутизации классификатора. */
export const TOP_FLAGS = { victims: 'victims', notOnSite: 'victims_not_on_site', noAccess: 'no_access' } as const;
const TOP_FLAG_CODES: string[] = Object.values(TOP_FLAGS);
/** ЧС / ЧП ставятся в режиме просмотра (п. 1.3), в опросной карте их нет. */
const NOT_IN_QUESTIONNAIRE = new Set([...TOP_FLAG_CODES, 'emergency', 'incident_flag']);

export const EMPTY_ADDRESS: CardAddress = {
  raw: '', country: 'Россия', region: 'Москва', city: 'Москва', object: '', okrug: null, district: null,
  street: '', house: '', building: '', structure: '', flat: '', entrance: '', floor: '', code: '', descriptive: '', lat: null, lon: null,
};

export interface CardState {
  phones: { aon: string; provided: string; on_site: string; foreign: boolean };
  channel: string;
  applicant: { name: string; status: string; foreign_language: boolean };
  topFlags: Record<keyof typeof TOP_FLAGS, boolean>;
  victimsCount: number;
  cardTypes: string[];
  /** Выбранный путь по дереву признаков для каждого типа «Что случилось?» */
  paths: Record<string, string[]>;
  /** Ответы Да/Нет на вопросы-признаки: {флаг: true | false} */
  flagAnswers: Record<string, boolean>;
  refusal103: boolean;
  address: CardAddress;
  description: string;
  removedAuto: string[];
  manual: string[];
  empty: null | 'no_contact' | 'call_dropped';
}

export function initialState(aon = '', channel = ''): CardState {
  return {
    phones: { aon, provided: '', on_site: '', foreign: false },
    channel,
    applicant: { name: '', status: '', foreign_language: false },
    topFlags: { victims: false, notOnSite: false, noAccess: false },
    victimsCount: 0,
    cardTypes: [],
    paths: {},
    flagAnswers: {},
    refusal103: false,
    address: { ...EMPTY_ADDRESS },
    description: '',
    removedAuto: [],
    manual: [],
    empty: null,
  };
}

export type Action =
  | { type: 'phone'; field: 'provided' | 'on_site'; value: string }
  | { type: 'foreign'; value: boolean }
  | { type: 'channel'; value: string }
  | { type: 'applicant'; patch: Partial<CardState['applicant']> }
  | { type: 'topFlag'; flag: keyof typeof TOP_FLAGS }
  | { type: 'victimsCount'; value: number }
  | { type: 'addType'; code: string }
  | { type: 'removeType'; code: string }
  | { type: 'choose'; cardType: string; level: number; label: string }
  | { type: 'flagAnswer'; flag: string; value: boolean }
  | { type: 'refusal103' }
  | { type: 'address'; patch: Partial<CardAddress> }
  | { type: 'clearAddress' }
  | { type: 'description'; value: string }
  | { type: 'removeService'; code: string; auto: boolean }
  | { type: 'serviceSelection'; selected: string[]; auto: string[] }
  | { type: 'empty'; kind: CardState['empty'] };

export function reducer(s: CardState, a: Action): CardState {
  switch (a.type) {
    case 'phone': return { ...s, phones: { ...s.phones, [a.field]: a.value } };
    case 'foreign': return { ...s, phones: { ...s.phones, foreign: a.value } };
    case 'channel': return { ...s, channel: a.value };
    case 'applicant': return { ...s, applicant: { ...s.applicant, ...a.patch } };
    case 'topFlag': {
      const on = !s.topFlags[a.flag];
      return { ...s, topFlags: { ...s.topFlags, [a.flag]: on }, victimsCount: a.flag === 'victims' && !on ? 0 : s.victimsCount };
    }
    case 'victimsCount': return { ...s, victimsCount: Math.max(0, Math.min(10_000, Math.trunc(a.value) || 0)) };
    case 'addType': return s.cardTypes.includes(a.code) ? s : { ...s, cardTypes: [...s.cardTypes, a.code] };
    case 'removeType': {
      const { [a.code]: _, ...paths } = s.paths;
      return { ...s, cardTypes: s.cardTypes.filter((c) => c !== a.code), paths, refusal103: a.code === '103' ? false : s.refusal103 };
    }
    case 'choose': {
      const path = (s.paths[a.cardType] ?? []).slice(0, a.level);
      // повторный клик по выбранному варианту снимает выбор (как чип в АРМ)
      const current = s.paths[a.cardType]?.[a.level];
      return { ...s, paths: { ...s.paths, [a.cardType]: current === a.label ? path : [...path, a.label] } };
    }
    case 'flagAnswer': {
      const same = s.flagAnswers[a.flag] === a.value;
      const { [a.flag]: _, ...rest } = s.flagAnswers;
      return { ...s, flagAnswers: same ? rest : { ...rest, [a.flag]: a.value } };
    }
    case 'refusal103': return { ...s, refusal103: !s.refusal103 };
    case 'address': return { ...s, address: { ...s.address, ...a.patch } };
    case 'clearAddress': return { ...s, address: { ...EMPTY_ADDRESS } };
    case 'description': return { ...s, description: a.value.slice(0, DESCRIPTION_MAX) };
    case 'removeService':
      return a.auto
        ? { ...s, removedAuto: [...new Set([...s.removedAuto, a.code])] }
        : { ...s, manual: s.manual.filter((c) => c !== a.code) };
    case 'serviceSelection':
      // модал «Добавьте службы»: снятые автоматические — в «убранные», новые — в «ручные»
      return {
        ...s,
        removedAuto: a.auto.filter((c) => !a.selected.includes(c)),
        manual: a.selected.filter((c) => !a.auto.includes(c)),
      };
    case 'empty': return { ...s, empty: a.kind };
  }
}

/* ---------------------------------------------------------------- дерево признаков */

/** Узлы на каждом уровне выбранного пути: [варианты уровня 0, варианты уровня 1, …]. */
export function levels(roots: TreeNode[], path: string[]): TreeNode[][] {
  const out: TreeNode[][] = [roots];
  let nodes = roots;
  for (const label of path) {
    const node = nodes.find((n) => n.label === label);
    if (!node || node.children.length === 0) break;
    nodes = node.children;
    out.push(nodes);
  }
  return out;
}

/** Конечный тип классификатора по выбранному пути; null — выбор не завершён. */
export function leafCode(roots: TreeNode[], path: string[]): string | null {
  let nodes = roots;
  let node: TreeNode | undefined;
  for (const label of path) {
    node = nodes.find((n) => n.label === label);
    if (!node) return null;
    nodes = node.children;
  }
  // узел с вариантами ниже, но без своего типа — выбор не завершён
  return node?.codes[0] ?? null;
}

/** Вопросы-признаки для опросной карты: флаги, которые в строке классификатора влияют на службы. */
export function flagQuestions(routingFlags: (string | null)[]): string[] {
  return [...new Set(routingFlags.filter((f): f is string => !!f && !NOT_IN_QUESTIONNAIRE.has(f)))];
}

/* ---------------------------------------------------------------- производные */

export function cardFlags(s: CardState): string[] {
  const top = (Object.keys(TOP_FLAGS) as (keyof typeof TOP_FLAGS)[]).filter((k) => s.topFlags[k]).map((k) => TOP_FLAGS[k]);
  const answered = Object.entries(s.flagAnswers).filter(([, v]) => v).map(([f]) => f);
  return [...new Set([...top, ...answered])];
}

export interface PanelService { code: string; short: string; main: boolean; integrated: boolean; auto: boolean; serviceType: string | null }

/** Панель служб = автоподбор − убранные вручную + добавленные вручную. */
export function panelServices(auto: ResolvedService[], s: CardState, catalog: Map<string, { short: string; integrated: boolean }>): PanelService[] {
  const autoShown = auto.filter((x) => !s.removedAuto.includes(x.code));
  const autoCodes = new Set(autoShown.map((x) => x.code));
  return [
    ...autoShown.map((x) => ({ code: x.code, short: x.short, main: x.main, integrated: x.integrated, auto: true, serviceType: x.service_type })),
    ...s.manual.filter((c) => !autoCodes.has(c)).map((c) => ({
      code: c, short: catalog.get(c)?.short ?? c, main: false, integrated: catalog.get(c)?.integrated ?? true, auto: false, serviceType: null,
    })),
  ];
}

/** Ответы опросной карты для эталона и оценки: путь по признакам + ответы Да/Нет по названию признака. */
export function questionnaireAnswers(s: CardState, flagsByType: Record<string, string[]>, flagName: (f: string) => string): CardData['questionnaire'] {
  const out: CardData['questionnaire'] = {};
  for (const ct of s.cardTypes) {
    const answers: Record<string, string> = {};
    (s.paths[ct] ?? []).forEach((label, i) => { answers[`Признак ${i + 1}`] = label; });
    for (const f of flagsByType[ct] ?? []) {
      if (f in s.flagAnswers) answers[flagName(f)] = s.flagAnswers[f] ? 'Да' : 'Нет';
    }
    if (ct === '103' && s.refusal103) answers['Отказ'] = 'Отказ от реагирования Скорой';
    out[ct] = answers;
  }
  return out;
}

/** Обратное преобразование сохранённой карточки — для показа в режиме просмотра. */
export function fromCardData(d: Partial<CardData>): CardState {
  const s = initialState(d.phones?.aon ?? '', d.channel ?? '');
  const flags = new Set(d.card_flags ?? []);
  const paths: Record<string, string[]> = {};
  for (const [ct, answers] of Object.entries(d.questionnaire ?? {})) {
    paths[ct] = [1, 2, 3].map((i) => answers[`Признак ${i}`]).filter((x): x is string => !!x);
  }
  return {
    ...s,
    phones: { ...s.phones, ...d.phones },
    applicant: { name: d.applicant?.name ?? '', status: d.applicant?.status ?? '', foreign_language: !!d.applicant?.foreign_language },
    topFlags: { victims: flags.has(TOP_FLAGS.victims), notOnSite: flags.has(TOP_FLAGS.notOnSite), noAccess: flags.has(TOP_FLAGS.noAccess) },
    victimsCount: d.victims?.count ?? 0,
    cardTypes: d.card_types ?? [],
    paths,
    flagAnswers: Object.fromEntries([...flags].filter((f) => !TOP_FLAG_CODES.includes(f)).map((f) => [f, true])),
    refusal103: !!d.flags?.refusal_103,
    address: { ...EMPTY_ADDRESS, ...d.address },
    description: d.description ?? '',
    empty: d.flags?.no_contact ? 'no_contact' : d.flags?.call_dropped ? 'call_dropped' : null,
  };
}

export function toCardData(s: CardState, incidentTypes: string[], questionnaire: CardData['questionnaire']): CardData {
  return {
    phones: s.phones,
    channel: s.channel || null,
    applicant: { name: s.applicant.name.trim(), status: s.applicant.status || null, foreign_language: s.applicant.foreign_language },
    victims: { has: s.topFlags.victims, count: s.topFlags.victims ? s.victimsCount : 0 },
    card_types: s.cardTypes,
    incident_types: incidentTypes,
    questionnaire,
    card_flags: cardFlags(s),
    address: s.address,
    description: s.description,
    flags: { no_contact: s.empty === 'no_contact', call_dropped: s.empty === 'call_dropped', refusal_103: s.refusal103, emergency: false, incident: false },
  };
}

export function toServicesIn(panel: PanelService[]): CardServiceIn[] {
  return panel.map((p) => ({ code: p.code, is_main: p.main, added_by: p.auto ? 'auto' : 'manual', service_type: p.serviceType }));
}

/** Клиентская проверка перед окном «Список оповещаемых служб» — те же правила, что на сервере. */
export function missingFields(s: CardState, incidentTypes: string[], pendingTypes: string[], panel: PanelService[]): string[] {
  const missing: string[] = [];
  if (s.cardTypes.length === 0) missing.push('Что случилось');
  for (const t of pendingTypes) missing.push(`Опросная карта «${t}»`);
  if (incidentTypes.length > 0) {
    const a = s.address;
    if (!(a.house || a.descriptive.trim() || (a.lat !== null && a.lon !== null))) missing.push('Адрес (дом, описательный адрес или координаты)');
    if (!s.applicant.name.trim()) missing.push('Фамилия и имя заявителя');
    if (!s.applicant.status) missing.push('Статус заявителя');
    if (!s.description.trim()) missing.push('Описание со слов заявителя');
    if (panel.length === 0) missing.push('Службы');
  }
  return missing;
}

/* ---------------------------------------------------------------- телефон и адрес */

/** «9179805413» → «+7 (917) 980-54-13» по мере ввода. */
export function formatPhone(raw: string): string {
  let d = raw.replace(/\D/g, '');
  if (d.startsWith('7') || d.startsWith('8')) d = d.slice(1);
  d = d.slice(0, 10);
  if (!d) return '';
  const parts = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 8), d.slice(8, 10)];
  let out = `+7 (${parts[0]}`;
  if (d.length >= 3) out += ')';
  if (parts[1]) out += ` ${parts[1]}`;
  if (parts[2]) out += `-${parts[2]}`;
  if (parts[3]) out += `-${parts[3]}`;
  return out;
}

/** Единая адресная строка: «Новая Басманная улица, 6 к1 с2» → улица, дом, корпус, строение.
 *  Справочника улиц и домов пока нет (п. 1.2) — разбор эвристический. */
export function parseAddressLine(raw: string): Pick<CardAddress, 'street' | 'house' | 'building' | 'structure'> {
  const text = raw.replace(/^\s*(г\.?\s*)?москва\s*,?/i, '').trim();
  const m = text.match(/^(.*?)[,\s]+(?:д\.?\s*|дом\s+|вл\.?\s*)?(\d+[а-яё]?(?:\/\d+)?)\s*(?:,?\s*(?:к\.?|корп\.?|корпус)\s*(\d+))?\s*(?:,?\s*(?:с\.?|стр\.?|строение)\s*(\d+))?\s*$/i);
  if (!m) return { street: text, house: '', building: '', structure: '' };
  return { street: m[1].replace(/,\s*$/, '').trim(), house: m[2], building: m[3] ?? '', structure: m[4] ?? '' };
}
