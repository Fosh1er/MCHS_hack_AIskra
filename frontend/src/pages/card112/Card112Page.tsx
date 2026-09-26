/** Карточка происшествия АРМ-112 (п. 1.1): раскладка стенда 2026, поведение — по инструкции (ADR-0008).
 *  /arm/112 — открыть новую карточку (Insert), /arm/112/:id — заполнение своей черновой или просмотр сохранённой. */
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { http } from '../../shared/api/http';
import { homeFor, useMe, type Me } from '../../shared/api/auth';
import {
  useCardTypes, useEnum, useResolvedServices, useServices, useTerritory,
  type IncidentTypeDetails, type Questionnaire,
} from '../../shared/api/dictionaries';
import { SERVICE_STATUS, useCard, useOpenCard, useSaveCard, type CardView } from '../../shared/api/incidents';
import { shortName } from '../../shared/ui/ArmTopBar';
import { CardHeader } from './CardHeader';
import { CardViewer } from './CardViewer';
import { CallPanel } from '../../shared/ui/CallPanel';
import { answerCall } from '../../shared/api/training';
import { ApplicantRow, VictimsRow } from './ApplicantBlock';
import { AddressBlock, DescriptionBlock } from './AddressBlock';
import { WhatHappened, cardTypeLabel } from './WhatHappened';
import { QuestionnairePanel } from './QuestionnairePanel';
import { ServicesBar, type SavedService } from './ServicesBar';
import { AddServicesModal, CloseCardModal, EmptyCardModal, SaveModal } from './Modals';
import { focusId, useHotkeys, type HotkeyMap } from './useHotkeys';
import {
  cardFlags, flagQuestions, fromCardData, initialState, leafCode, missingFields, panelServices,
  questionnaireAnswers, reducer, toCardData, toServicesIn,
} from './state';

const hhmm = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '');

/** /arm/112 — открывает карточку на сервере (номер, время регистрации) и переходит к ней. */
export function Card112NewPage() {
  const open = useOpenCard();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return; // StrictMode вызывает эффект дважды — карточка открывается один раз
    started.current = true;
    open.mutate(
      { aon: params.get('aon') ?? '', channel: params.get('channel') },
      { onSuccess: (c) => navigate(`/arm/112/${c.id}`, { replace: true }) },
    );
  }, [open, navigate, params]);
  return <div className="arm112"><p className="arm-empty" style={{ padding: 24 }}>{open.isError ? `Не удалось открыть карточку: ${open.error.message}` : 'Открытие карточки…'}</p></div>;
}

/** Разговор с ИИ-заявителем (п. 1.4): звонок принимается один раз при открытии карточки по входящему вызову
 *  и остаётся на экране после сохранения — оператор может договорить и завершить. */
function IncomingCallDock({ callId, cardId, aon }: { callId: string; cardId: string; aon: string }) {
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(true);
  const answered = useRef(false);
  useEffect(() => {
    if (answered.current) return;
    answered.current = true;
    answerCall(callId, cardId).finally(() => setReady(true));
  }, [callId, cardId]);
  if (!ready || !open) return null;
  return <CallPanel callId={callId} title={`Заявитель · ${aon}`} subtitle="Уточните адрес, что случилось, пострадавших, ФИО" partyName="Заявитель" onClose={() => setOpen(false)} />;
}

export function Card112Page() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const card = useCard(id);
  const me = useMe().data!;
  if (card.isPending) return <div className="arm112" />;
  if (card.isError) return <div className="arm112"><p className="arm-empty" style={{ padding: 24 }}>{card.error.message}</p></div>;
  const callId = params.get('call');
  const dock = callId && card.data.author_id === me.user_id
    ? <IncomingCallDock callId={callId} cardId={card.data.id} aon={card.data.data.phones?.aon ?? ''} />
    : null;
  const editable = card.data.status === 'draft' && card.data.author_id === me.user_id;
  // сохранённая карточка — экран просмотра (п. 1.3); чужой черновик преподаватель видит в раскладке заполнения
  if (card.data.status !== 'draft') return <>{<CardViewer key={card.data.id} view={card.data} me={me} />}{dock}</>;
  return <>{<CardEditor key={`${card.data.id}:${card.data.status}`} view={card.data} editable={editable} me={me} />}{dock}</>;
}

type ModalKind = null | 'services' | 'save' | 'close' | 'new' | 'no_contact' | 'call_dropped';

function CardEditor({ view, editable, me }: { view: CardView; editable: boolean; me: Me }) {
  const readOnly = !editable;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [state, dispatch] = useReducer(reducer, view, (v) => (editable ? initialState(v.data.phones?.aon ?? '', v.data.channel ?? '') : fromCardData(v.data)));
  const [modal, setModal] = useState<ModalKind>(null);
  const [banner, setBanner] = useState<{ title: string; items: string[] } | null>(null);
  const save = useSaveCard(view.id);
  const qRefs = useRef<(HTMLDivElement | null)[]>([]);

  // --- справочники
  const cardTypes = useCardTypes();
  const statuses = useEnum('applicant_status');
  const channels = useEnum('channel');
  const flagEnum = useEnum('card_flag');
  const territory = useTerritory();
  const allServices = useServices();
  const flagNames = useMemo(() => new Map((flagEnum.data ?? []).map((f) => [f.code, f])), [flagEnum.data]);
  const serviceCatalog = useMemo(() => new Map((allServices.data ?? []).map((s) => [s.code, s])), [allServices.data]);

  // --- опросные карты и конечные типы классификатора
  const trees = useQueries({
    queries: state.cardTypes.map((ct) => ({
      queryKey: ['dict', 'questionnaire', ct],
      queryFn: () => http<Questionnaire>(`/api/v1/dictionaries/card-types/${encodeURIComponent(ct)}/questionnaire`),
      staleTime: Infinity,
    })),
  });
  const leaves = state.cardTypes.map((ct, i) => {
    const tree = trees[i]?.data;
    return tree ? leafCode(tree.roots, state.paths[ct] ?? []) : null;
  });
  const labelOf = (ct: string) => {
    const t = cardTypes.data?.find((x) => x.code === ct);
    return t ? cardTypeLabel(t) : ct;
  };
  const pendingTypes = state.cardTypes.filter((_, i) => (trees[i]?.data?.roots.length ?? 0) > 0 && !leaves[i]).map(labelOf);
  const incidentTypes = [...new Set(leaves.filter((x): x is string => !!x))];
  const details = useQueries({
    queries: leaves.map((code) => ({
      queryKey: ['dict', 'incident-type', code],
      queryFn: () => http<IncidentTypeDetails>(`/api/v1/dictionaries/incident-types/${code}`),
      enabled: !!code,
      staleTime: Infinity,
    })),
  });
  const flagsByType: Record<string, string[]> = Object.fromEntries(
    state.cardTypes.map((ct, i) => [ct, flagQuestions((details[i]?.data?.routing ?? []).filter((c) => c.audience === 'card').map((c) => c.flag))]),
  );

  // --- службы: автоподбор по классификатору, признакам и адресу + ручные правки
  const flags = cardFlags(state);
  const resolved = useResolvedServices(incidentTypes, flags, state.address.okrug, state.address.district);
  const auto = editable && incidentTypes.length ? resolved.data?.services ?? [] : [];
  const panel = panelServices(auto, state, serviceCatalog);
  // порядок служб — как на панели в момент сохранения (data.services), основная — первой
  const order = (code: string) => { const i = view.data.services?.indexOf(code) ?? -1; return i < 0 ? 999 : i; };
  const savedServices: SavedService[] | null = readOnly
    ? [...view.services].sort((a, b) => Number(b.is_main) - Number(a.is_main) || order(a.code) - order(b.code)).map((s) => ({ code: s.code, short: s.short, is_main: s.is_main, integrated: s.integrated, status: `${hhmm(s.status_at)} ${SERVICE_STATUS[s.status] ?? s.status}` }))
    : null;

  // --- таймер: от открытия до сохранения
  const openedAt = view.opened_at ? new Date(view.opened_at).getTime() : Date.now();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (readOnly) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [readOnly]);
  const seconds = readOnly ? Math.round((view.processing_ms ?? 0) / 1000) : Math.max(0, Math.floor((now - openedAt) / 1000));

  // --- действия
  const flagName = (f: string) => flagNames.get(f)?.name ?? f;
  const submit = (empty: 'no_contact' | 'call_dropped' | null) => {
    const s = { ...state, empty };
    const data = empty ? toCardData(s, [], {}) : toCardData(s, incidentTypes, questionnaireAnswers(s, flagsByType, flagName));
    save.mutate(
      { data, services: empty ? [] : toServicesIn(panel) },
      {
        onSuccess: () => { setModal(null); qc.invalidateQueries({ queryKey: ['card', view.id] }); },
        onError: (e) => { setModal(null); setBanner({ title: 'Карточка не сохранена', items: [e.message] }); },
      },
    );
  };
  const trySave = () => {
    if (readOnly) return;
    const missing = missingFields(state, incidentTypes, pendingTypes, panel);
    if (missing.length) setBanner({ title: 'Заполните обязательные поля:', items: missing });
    else { setBanner(null); setModal('save'); }
  };
  const home = () => navigate(homeFor(me));
  const closeCard = () => (editable ? setModal('close') : home());
  const newCard = () => (editable ? setModal('new') : navigate('/arm/112'));
  useEffect(() => {
    if (!banner) return;
    const t = setTimeout(() => setBanner(null), 8000);
    return () => clearTimeout(t);
  }, [banner]);

  // --- горячие клавиши (docs/brief/03 §6)
  const altKeys: HotkeyMap = modal ? {} : {
    F1: focusId('phone-aon'), F2: focusId('phone-provided'), F3: focusId('phone-on-site'),
    KeyK: focusId('channel'), KeyQ: focusId('applicant-name'), KeyA: focusId('address-line'),
    KeyP: focusId('victims'), KeyT: focusId('what-happened'), KeyR: focusId('significant-first'),
    KeyO: focusId('description'),
    ...(editable && { KeyN: () => setModal('no_contact'), KeyZ: () => setModal('services'), KeyS: trySave }),
    ...Object.fromEntries([1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => [`Digit${n}`, () => qRefs.current[n - 1]?.focus()])),
  };
  const plainKeys: HotkeyMap = modal ? { Escape: () => setModal(null) } : { Escape: closeCard, Insert: newCard };
  const altHeld = useHotkeys(altKeys, plainKeys);

  const operator = `${view.operator_number ?? me.operator_number ?? ''}, АРМ ${view.arm_number ?? me.arm_number ?? '—'}, ${shortName(view.author_name ?? me.full_name)}`;
  const ambulance = state.cardTypes.includes('103') || panel.some((s) => s.code === 'S103') || view.services.some((s) => s.code === 'S103');

  return (
    <div className={`arm112${altHeld ? ' arm112--alt' : ''}${readOnly ? ' arm112-saved' : ''}`}>
      <CardHeader
        state={state} dispatch={dispatch} readOnly={readOnly} seconds={seconds}
        info={{ number: view.number, registeredAt: view.opened_at ? new Date(view.opened_at) : null, savedAt: view.saved_at ? new Date(view.saved_at) : null, operator }}
      />
      <div className="arm112__body">
        <ApplicantRow state={state} dispatch={dispatch} statuses={statuses.data ?? []} channels={channels.data ?? []} readOnly={readOnly} />
        <VictimsRow state={state} dispatch={dispatch} readOnly={readOnly} onEmpty={(kind) => setModal(kind)} />
        <div className="arm112__col">
          <AddressBlock state={state} dispatch={dispatch} okrugs={territory.data?.okrugs ?? []} districts={territory.data?.districts ?? []} readOnly={readOnly} />
          <DescriptionBlock state={state} dispatch={dispatch} ambulance={ambulance} readOnly={readOnly} />
        </div>
        <div className="arm112__col">
          <WhatHappened all={cardTypes.data ?? []} selected={state.cardTypes} onAdd={(code) => dispatch({ type: 'addType', code })} readOnly={readOnly} />
          {readOnly && state.empty && <div className="arm-panel"><b>{state.empty === 'no_contact' ? '<Нет контакта>' : '<Срыв связи>'}</b> — карточка сохранена пустой</div>}
          {state.cardTypes.length > 0 && (
            <div className="arm112-tabs">
              {state.cardTypes.map((ct, i) => {
                const label = labelOf(ct);
                return (
                  <button key={ct} type="button" className={`arm112-tab${pendingTypes.includes(label) ? ' arm112-tab--pending' : ''}`}
                    title={`Alt+${i + 1}`} onClick={() => qRefs.current[i]?.focus()}>{label}</button>
                );
              })}
            </div>
          )}
          <div className="arm112__scroll">
            {state.cardTypes.map((ct, i) => (
              <QuestionnairePanel
                key={ct} ref={(el) => { qRefs.current[i] = el; }} cardType={ct} index={i} tree={trees[i]?.data}
                path={state.paths[ct] ?? []} flags={flagsByType[ct] ?? []} flagAnswers={state.flagAnswers} flagNames={flagNames}
                refusal103={state.refusal103} readOnly={readOnly} dispatch={dispatch}
              />
            ))}
            {editable && resolved.data?.needs_address && incidentTypes.length > 0 && (
              <div className="arm-panel arm-panel__label">Укажите округ и район в адресе — добавятся территориальные службы (префектура, ДДС района).</div>
            )}
          </div>
        </div>
      </div>

      {banner && (
        <div className="arm112-banner" role="alert" onClick={() => setBanner(null)}>
          <b>{banner.title}</b>
          <ul>{banner.items.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      )}

      <ServicesBar
        panel={panel} saved={savedServices} busy={save.isPending}
        onRemove={(s) => dispatch({ type: 'removeService', code: s.code, auto: s.auto })}
        onAdd={() => setModal('services')} onSave={trySave} onClose={closeCard} onNew={newCard}
      />

      {modal === 'services' && (
        <AddServicesModal
          all={allServices.data ?? []} selected={panel.map((s) => s.code)} onClose={() => setModal(null)}
          onSave={(codes) => { dispatch({ type: 'serviceSelection', selected: codes, auto: auto.map((s) => s.code) }); setModal(null); }}
        />
      )}
      {modal === 'save' && <SaveModal services={panel} busy={save.isPending} onConfirm={() => submit(null)} onClose={() => setModal(null)} />}
      {(modal === 'no_contact' || modal === 'call_dropped') && (
        <EmptyCardModal kind={modal} busy={save.isPending} onConfirm={() => submit(modal)} onClose={() => setModal(null)} />
      )}
      {(modal === 'close' || modal === 'new') && (
        <CloseCardModal onClose={() => setModal(null)} onConfirm={modal === 'new' ? () => navigate('/arm/112') : home} />
      )}
    </div>
  );
}
