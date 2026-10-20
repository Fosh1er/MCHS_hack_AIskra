/** Панель разговора (п. 1.4, 2.3): реплики оператора и ИИ-собеседника, таймер, «завершить».
 *  Голос (P1): реплики собеседника озвучиваются синтезом речи браузера (Web Speech API работает офлайн на ОС
 *  с русским голосом); оператор говорит в микрофон — запись распознаёт Whisper на сервере (`POST /training/speech`),
 *  либо печатает. Вид — тёмный док АРМ (ui-kit: Transcript, Composer).
 *  Эмоции (п. 3.6): у реплики заявителя — его состояние; голос следует ему темпом, высотой и громкостью,
 *  а в тексте состояние видно подписью у реплики — в текстовом режиме это единственный канал интонации.
 *  Если на сервере настроен синтез (`GET /training/speech` → `tts`), реплика звучит голосом модели с эмоцией;
 *  сбой синтеза — та же реплика голосом браузера.
 *  Без рук (п. 3.6, V3): микрофон открыт на время звонка, фразы оператора выделяются по голосу (`VadDetector`),
 *  распознаются и уходят собеседнику по очереди; оператор заговорил — собеседник замолкает (перебивание). */
import { useEffect, useRef, useState } from 'react';
import { Composer, Icon, Transcript, type TranscriptMessage } from '@smena112/ui-kit';
import { ApiError } from '../api/http';
import { endCall, getCall, pauseCall, replicaAudioUrl, sendReplica, speakUrl, streamReplica, tickCall, transcribe, useSpeechStatus, type CallMessage, type PsyLive, type Replica, type ReplicaVia, type StreamMetrics, type Tone } from '../api/training';
import { useActiveTour } from '../onboarding/OnboardingProvider';
import { useHandsFree, type HandsFreeState } from '../voice/useHandsFree';
import { VAD_PROFILES, isLikelyEcho, type VadProfileName } from '../voice/vad';

/** Ремарки заявителя (п. 3.7): «плачет», «кричит» — показываются курсивом перед репликой, в озвучку не идут. */
const note = (m: CallMessage) => (m.remarks && m.remarks.length ? `(${m.remarks.join(', ')})` : undefined);

/** Реплика в панели: `aiLine` — кто и как быстро написал ответ (F1), `voiced` — уже озвучена по фразам во время потока. */
type Msg = CallMessage & { aiLine?: string; voiced?: boolean };
/** Ответ, который ещё генерируется (F1). */
interface Live { text: string; fresh: string; tone?: Tone | null; model?: string; remarks: string[]; replaced: boolean }

const sec = (ms: number) => `${(ms / 1000).toFixed(1).replace('.', ',')} с`;
/** «ИИ · demo-m · первое слово 0,4 с · ответ 2,1 с» или «ответ по правилам» — честно, без имитации модели. */
function metricsLine(m: StreamMetrics): string {
  if (m.source === 'rules') return m.replaced ? 'ответ модели отклонён проверкой — ответ по правилам' : 'ответ по правилам (без модели)';
  const parts = ['ИИ', m.model ?? 'модель'];
  if (m.ttft_ms != null) parts.push(`первое слово ${sec(m.ttft_ms)}`);
  parts.push(`ответ ${sec(m.total_ms)}`);
  if (m.pieces_per_s) parts.push(`${String(m.pieces_per_s).replace('.', ',')} ток/с`);
  return parts.join(' · ');
}
/** Граница фразы для озвучки по ходу генерации: знак конца предложения и пробел после него. */
const SENTENCE = /^[\s\S]*?[.!?…]+(?=\s)/;

const ECCS_TITLE: Record<number, string> = { 1: 'спокоен', 2: 'тревожен, сотрудничает', 3: 'расстроен, сотрудничает', 4: 'не сотрудничает', 5: 'неуправляем' };
/** Шкала состояния заявителя с психологическим профилем (п. 3.7, F4): уровень ECCS 1–5 и что его изменило. */
function PsyMeter({ level, title, last }: { level: number; title?: string; last?: PsyLive | null }) {
  const change = last ? last.level_after - last.level_before : 0;
  const why = last?.deltas.filter((d) => d.change !== 0).map((d) => last.acts.find((a) => a.code === d.cause)?.title ?? d.note ?? d.cause).filter(Boolean);
  return (
    <div className="call-psy" role="status" aria-live="polite" title="Шкала эмоционального состояния ECCS (IAED): 1 — спокоен, 5 — неуправляем">
      <span className="call-psy__label">Состояние · ECCS {level}/5</span>
      <span className="call-psy__bar" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((n) => <span key={n} className={`call-psy__seg${n <= level ? ` is-on is-l${level}` : ''}`} />)}
      </span>
      <span className="call-psy__title">{title ?? ECCS_TITLE[level]}</span>
      {change !== 0 && why && why.length > 0 && (
        <span className={`call-psy__why ${change > 0 ? 'is-up' : 'is-down'}`}>{change > 0 ? '▲' : '▼'} {why.join('; ')}</span>
      )}
    </div>
  );
}

const pad = (n: number) => String(n).padStart(2, '0');
const MAX_TALK_MS = 30_000; // реплика в трубку — не дольше 30 с, дальше запись останавливается сама

/** Запись реплики с микрофона: «говорить» → запись → «готово» → Whisper → текст. */
function useTalk(onText: (text: string) => void, onError: (msg: string) => void) {
  const [state, setState] = useState<'idle' | 'starting' | 'recording' | 'recognizing'>('idle');
  const [since, setSince] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stopTimer = useRef<number>();
  const stop = () => { if (rec.current?.state === 'recording') rec.current.stop(); };
  const start = async () => {
    if (state !== 'idle') return;
    setState('starting'); // первое открытие микрофона (разрешение браузера) может занять секунды
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm'].find((m) => MediaRecorder.isTypeSupported(m));
      const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      r.onstop = async () => {
        window.clearTimeout(stopTimer.current);
        stream.getTracks().forEach((t) => t.stop());
        setState('recognizing');
        try {
          const text = (await transcribe(new Blob(chunks, { type: r.mimeType || 'audio/webm' }))).trim();
          if (text) onText(text); else onError('Не расслышал — повторите или напечатайте реплику');
        } catch (e) { onError((e as Error).message); }
        setState('idle');
      };
      rec.current = r;
      r.start();
      setSince(Date.now());
      setState('recording');
      stopTimer.current = window.setTimeout(stop, MAX_TALK_MS);
    } catch {
      setState('idle');
      onError('Нет доступа к микрофону — разрешите его в браузере');
    }
  };
  useEffect(() => () => { window.clearTimeout(stopTimer.current); stop(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return { state, since, start, stop };
}
const VOICE_KEY = 'aiskra.call.voice';
const HANDS_FREE_KEY = 'aiskra.call.handsfree';
const VAD_KEY = 'aiskra.call.vad';
const stored = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const store = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* приватный режим */ } };
const HANDS_FREE_TEXT: Record<HandsFreeState, string> = {
  off: '', starting: 'включаю микрофон…', calibrating: 'слушаю фон — помолчите секунду', listening: 'слушаю',
  party: 'собеседник говорит — можно перебить', hearing: 'слышу вас…', error: 'микрофон недоступен',
};

/** Подача голоса по состоянию заявителя (п. 3.6, спецификация — таблица 7.3). Нет состояния — ровный голос. */
const RATE: Record<Tone['pace'], number> = { slow: 0.9, normal: 1, fast: 1.15, very_fast: 1.3 };
const VOLUME: Record<Tone['volume'], number> = { whisper: 0.5, low: 0.8, normal: 0.9, loud: 1 };
function prosody(tone?: Tone | null) {
  if (!tone) return { rate: 1, pitch: 1, volume: 1 };
  const pitch = tone.tension <= 3 ? 0.95 : tone.tension <= 5 ? 1 : tone.tension <= 7 ? 1.08 : 1.15;
  return { rate: RATE[tone.pace] ?? 1, pitch, volume: VOLUME[tone.volume] ?? 1 };
}

function speak(text: string, tone?: Tone | null) {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'ru-RU';
    const p = prosody(tone);
    u.rate = p.rate;
    u.pitch = p.pitch;
    u.volume = p.volume;
    const voice = synth.getVoices().find((v) => v.lang.startsWith('ru'));
    if (voice) u.voice = voice;
    synth.cancel();
    synth.speak(u);
  } catch { /* синтез недоступен — остаётся текст */ }
}

export function CallPanel({ callId, title, subtitle, partyName, initial, onEnded, onClose }: {
  callId: string; title: string; subtitle?: string; partyName: string; initial?: CallMessage[];
  onEnded?: () => void; onClose?: () => void;
}) {
  const [messages, setMessages] = useState<Msg[]>(initial ?? []);
  const [live, setLive] = useState<Live | null>(null);
  const [psyLevel, setPsyLevel] = useState<{ level: number; title?: string; last?: PsyLive | null } | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState('');
  const [startedAt, setStartedAt] = useState<number>(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [voice, setVoice] = useState(() => { try { return localStorage.getItem(VOICE_KEY) === '1'; } catch { return false; } });
  const [psy, setPsy] = useState(false); // п. 3.7: у заявителя психологический профиль — доступна «Пауза»
  // панель плавает поверх карточки и на экранах до ~1600 px закрывает её правую часть — её можно свернуть в одну
  // полосу; режим «без рук» при этом продолжает слушать, а напечатать реплику — развернуть
  const [collapsed, setCollapsed] = useState(false);
  const [branching, setBranching] = useState(false); // F5: ветвящийся сценарий — ситуация меняется и без реплик
  const spoken = useRef(0);
  const audio = useRef<HTMLAudioElement | null>(null);
  const lastParty = useRef<{ text: string; at: number } | null>(null); // для отсева эха собеседника
  const status = useSpeechStatus();
  const serverVoice = status.data?.tts ?? false;

  const phrases = useRef<HTMLAudioElement[]>([]); // F1: фразы ответа, ждущие озвучки (звук уже грузится)
  const spokenUpTo = useRef(0);
  const stopVoice = () => {
    phrases.current.forEach((a) => { a.src = ''; });
    phrases.current = [];
    audio.current?.pause();
    audio.current = null;
    try { window.speechSynthesis?.cancel(); } catch { /* нет синтеза */ }
  };
  /** Реплика собеседника: серверный голос с эмоцией, при сбое — голос браузера. */
  const play = (m: CallMessage) => {
    stopVoice();
    lastParty.current = { text: m.text, at: Date.now() };
    if (!serverVoice || !m.id) { speak(m.text, m.tone); return; }
    const a = new Audio(replicaAudioUrl(callId, m.id));
    audio.current = a;
    let fellBack = false;
    const fallback = () => {
      if (fellBack || audio.current !== a) return; // уже заменена следующей репликой или остановлена
      fellBack = true;
      audio.current = null;
      speak(m.text, m.tone);
    };
    a.onerror = fallback;
    a.play().catch((e: DOMException) => { if (e.name !== 'AbortError') fallback(); });
  };
  useEffect(() => () => stopVoice(), []); // eslint-disable-line react-hooks/exhaustive-deps
  // панель плавает над карточкой: пока она открыта, у прокрутки карточки снизу запас, чтобы последние строки
  // (опросная карта) можно было поднять над панелью
  useEffect(() => {
    document.body.classList.add('has-call-panel');
    return () => document.body.classList.remove('has-call-panel');
  }, []);

  /** F1: озвучка по фразам, пока ответ ещё пишется. Только серверный голос — браузерный говорит реплику целиком. */
  const playPhrases = () => {
    const a = audio.current ? undefined : phrases.current.shift();
    if (!a) return;
    audio.current = a;
    const next = () => { if (audio.current === a) { audio.current = null; playPhrases(); } };
    a.onended = next;
    a.onerror = next;
    a.play().catch(next);
  };
  const sayPhrase = (text: string, tone?: Tone | null) => {
    const t = text.trim();
    if (t.length < 2) return;
    lastParty.current = { text: (lastParty.current?.text ?? '') + ' ' + t, at: Date.now() };
    const a = new Audio(speakUrl(callId, t, tone)); // синтез начинается сразу, пока звучит предыдущая фраза
    a.preload = 'auto';
    phrases.current.push(a);
    playPhrases();
  };
  const feedPhrases = (text: string, tone?: Tone | null) => {
    for (let rest = text.slice(spokenUpTo.current), m = SENTENCE.exec(rest); m; m = SENTENCE.exec(rest)) {
      sayPhrase(m[0], tone);
      spokenUpTo.current += m[0].length;
      rest = text.slice(spokenUpTo.current);
    }
  };

  useEffect(() => {
    getCall(callId).then((c) => {
      setMessages(c.messages);
      setStartedAt(new Date(c.answered_at ?? c.started_at).getTime());
      setEnded(c.status === 'ended');
      setPsy(!!c.psy);
      if (c.psy) setPsyLevel({ level: c.psy.level });
      setBranching(!!c.branching);
    }).catch(() => undefined);
  }, [callId]);
  const busyRef = useRef(false);
  busyRef.current = busy;
  // F5: таймер ситуации — раз в 5 с, пока звонок идёт: «Дым уже в коридоре!» звучит, даже если оператор молчит
  useEffect(() => {
    if (!branching || ended) return;
    const t = setInterval(() => {
      if (busyRef.current) return; // ответ на реплику сам продвинет ситуацию
      tickCall(callId).then((events) => {
        if (!events.length) return;
        setMessages((m) => [...m, ...events.map((e) => ({
          speaker: e.speaker, text: e.text, at: new Date().toISOString(), id: e.message_id, tone: e.tone, remarks: e.remarks,
        }))]);
      }).catch(() => undefined);
    }, 5000);
    return () => clearInterval(t);
  }, [branching, ended, callId]);
  useEffect(() => { if (ended) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, [ended]);
  useEffect(() => {
    if (status.isLoading) return; // сначала узнаём, есть ли серверный голос, — иначе первую реплику скажет браузер
    const party = messages.filter((m) => m.speaker === 'party');
    const last = party[party.length - 1];
    if (voice && party.length > spoken.current && !last.voiced) play(last);
    spoken.current = party.length;
  }, [messages, voice, status.isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const endedRef = useRef(ended);
  endedRef.current = ended;
  const deliver = async (t: string, via: ReplicaVia) => {
    setBusy(true);
    setError('');
    setMessages((m) => [...m, { speaker: 'operator', text: t, at: new Date().toISOString() }]);
    const phrased = voice && serverVoice; // озвучка по фразам — пока ответ пишется
    const cur: Live = { text: '', fresh: '', remarks: [], replaced: false };
    spokenUpTo.current = 0;
    if (phrased) stopVoice();
    try {
      let r: Replica & { metrics?: StreamMetrics };
      try {
        r = await streamReplica(callId, t, via, {}, (e) => {
          if (e.type === 'state') {
            cur.tone = e.tone ?? cur.tone;
            if (e.psy) { const p = e.psy; setPsy(true); setPsyLevel({ level: p.level_after, title: p.level_title, last: p }); }
          } else if (e.type === 'model') cur.model = e.model;
          else if (e.type === 'offline') cur.model = undefined; // модель не ответила — без подписи «ИИ думает»
          else if (e.type === 'token') {
            cur.text += e.text;
            cur.fresh = e.text;
            if (phrased && !cur.replaced) feedPhrases(cur.text, cur.tone);
          } else if (e.type === 'remark') cur.remarks.push(e.text);
          else if (e.type === 'replace') { cur.replaced = true; if (phrased) stopVoice(); }
          setLive({ ...cur });
        });
      } catch (e) {
        if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 405)) throw e;
        r = await sendReplica(callId, t, via); // сервер без потока — ответ целиком
      }
      const voiced = phrased && spokenUpTo.current > 0 && !cur.replaced;
      if (voiced) sayPhrase(r.text.slice(spokenUpTo.current), r.tone ?? cur.tone); // хвост после последней фразы
      if (r.voice) setPsy(true);
      setMessages((m) => [...m, {
        speaker: r.speaker, text: r.text, at: new Date().toISOString(), id: r.message_id, tone: r.tone, remarks: r.remarks,
        aiLine: r.metrics ? metricsLine(r.metrics) : undefined, voiced,
      }]);
      if (r.hung_up) { // заявитель положил трубку — по ПП РФ № 1931 обратный вызов через 10 с
        setMessages((m) => [...m, { speaker: 'system', text: 'Заявитель положил трубку. Перезвоните ему по номеру АОН.', at: new Date().toISOString() }]);
        setEnded(true);
        onEnded?.();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLive(null);
      setBusy(false);
    }
  };
  const send = async () => {
    const t = text.trim();
    if (!t || busy || ended) return;
    setText('');
    await deliver(t, 'text');
  };
  /** Голосовые реплики — по очереди: сказанное, пока собеседник отвечает, не теряется, а его ответ не обрывается —
   *  он уже сохранён в звонке и участвует в автооценке. */
  const pending = useRef<{ text: string; via: ReplicaVia }[]>([]);
  const draining = useRef(false);
  const enqueue = async (t: string, via: ReplicaVia) => {
    pending.current.push({ text: t, via });
    if (draining.current) return;
    draining.current = true;
    try {
      for (let next = pending.current.shift(); next && !endedRef.current; next = pending.current.shift()) {
        await deliver(next.text, next.via);
      }
    } finally {
      pending.current = [];
      draining.current = false;
    }
  };
  const pause = async () => { // п. 3.7: тяжёлый звонок можно остановить — он не оценивается
    await pauseCall(callId).catch(() => undefined);
    stopVoice();
    setMessages((m) => [...m, { speaker: 'system', text: 'Звонок остановлен (пауза) — в работе с заявителем не оценивается', at: new Date().toISOString() }]);
    setEnded(true);
    onEnded?.();
  };
  const hangup = async () => {
    if (!ended) await endCall(callId).catch(() => undefined);
    stopVoice();
    setEnded(true);
    onEnded?.();
  };
  const speech = status.data?.enabled ?? false;
  const secure = typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices;
  const talk = useTalk((t) => { setError(''); void enqueue(t, 'voice'); }, setError);

  const [handsFree, setHandsFree] = useState(() => stored(HANDS_FREE_KEY) === '1');
  const [vadProfile, setVadProfile] = useState<VadProfileName>(() => {
    const v = stored(VAD_KEY);
    return v && v in VAD_PROFILES ? (v as VadProfileName) : 'balanced'; // в классе несколько операторов — не «высокая»
  });
  const [recognizing, setRecognizing] = useState(0);
  const tour = useActiveTour(); // на время подсказок микрофон закрыт (п. 5.3)
  const handsFreeOn = handsFree && speech && secure && !ended && !tour;
  const hf = useHandsFree({
    enabled: handsFreeOn,
    profile: vadProfile,
    partySpeaking: () => (!!audio.current && !audio.current.paused) || (window.speechSynthesis?.speaking ?? false),
    onSpeechStart: stopVoice, // перебивание
    onPhrase: async (blob) => {
      setRecognizing((n) => n + 1);
      try {
        const t = (await transcribe(blob)).trim();
        if (!t || isLikelyEcho(t, lastParty.current, Date.now())) return; // шум или голос собеседника из динамиков
        setError('');
        void enqueue(t, 'hands_free');
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setRecognizing((n) => n - 1);
      }
    },
    onError: (m) => { setError(m); setHandsFree(false); },
  });
  const toggleHandsFree = () => {
    const v = !handsFree;
    setHandsFree(v);
    store(HANDS_FREE_KEY, v ? '1' : '0');
  };
  const hfText = tour && handsFree ? 'микрофон выключен на время подсказок' : recognizing > 0 && hf !== 'hearing' ? 'распознаю…' : HANDS_FREE_TEXT[hf];
  const talkSecs = talk.state === 'recording' ? Math.floor((now - talk.since) / 1000) : 0;
  const toggleVoice = () => {
    const v = !voice;
    if (!v) stopVoice();
    setVoice(v);
    store(VOICE_KEY, v ? '1' : '0');
  };

  const secs = Math.max(0, Math.floor(((ended ? now : now) - startedAt) / 1000));
  const transcript: TranscriptMessage[] = messages.map((m) => ({
    from: m.speaker === 'operator' ? 'me' : m.speaker === 'party' ? 'them' : 'sys',
    who: m.speaker === 'operator' ? 'Вы' : m.tone ? `${partyName} · ${m.tone.emotion_title}` : partyName,
    text: m.text,
    note: m.speaker === 'party' ? note(m) : undefined,
    meta: m.aiLine,
  }));
  if (live && live.text) {
    transcript.push({
      from: 'them', who: live.tone ? `${partyName} · ${live.tone.emotion_title}` : partyName,
      text: live.text, fresh: live.fresh, streaming: true, replaced: live.replaced,
      note: live.remarks.length ? `(${live.remarks.join(', ')})` : undefined,
      meta: live.replaced ? 'ответ модели не прошёл проверку — заменяется' : `ИИ генерирует ответ · ${live.model ?? 'модель'}`,
    });
  } else if (busy) {
    transcript.push({ from: 'sys', text: live?.model ? `${partyName} отвечает · ИИ ${live.model} думает…` : `${partyName} отвечает…` });
  }

  return (
    <aside className={`call-panel arm-dock${collapsed ? ' call-panel--collapsed' : ''}`} aria-label={`Разговор: ${title}`}>
      <div className="arm-dock__section">
        <div className="arm-dock__title">
          <span><Icon name="phone" size="sm" /> {title}</span>
          <span className="call-panel__head">
            <span className="call-panel__timer" aria-label="Длительность разговора">{ended ? 'завершён' : `${pad(Math.floor(secs / 60))}:${pad(secs % 60)}`}</span>
            <button type="button" className="call-panel__fold" aria-expanded={!collapsed}
              title={collapsed ? 'Развернуть разговор' : 'Свернуть разговор в полосу — открыть карточку под ним'}
              onClick={() => setCollapsed((c) => !c)}>{collapsed ? 'развернуть' : 'свернуть'}</button>
          </span>
        </div>
        {collapsed
          ? <div className="call-panel__sub call-panel__last">{live?.text || [...messages].reverse().find((m) => m.speaker === 'party')?.text || subtitle}</div>
          : subtitle && <div className="call-panel__sub">{subtitle}</div>}
      </div>
      <div className="arm-dock__section arm-dock__section--grow">
        {psyLevel && <PsyMeter level={psyLevel.level} title={psyLevel.title} last={psyLevel.last} />}
        <Transcript messages={transcript} />
        {error && <div className="call-panel__err" role="alert">{error}</div>}
        {!ended && <Composer value={text} onChange={setText} onSend={() => { void send(); }} />}
        {!ended && speech && handsFree && (
          <div className={`call-panel__hf is-${hf}`} role="status" aria-live="polite">
            <span className="call-panel__hf-dot" aria-hidden="true" />
            <span className="call-panel__hf-text">{hfText}</span>
            <select className="call-panel__hf-level" value={vadProfile} aria-label="Чувствительность микрофона"
              title="Чувствительность: как громко нужно говорить, чтобы фраза началась"
              onChange={(e) => { const v = e.target.value as VadProfileName; setVadProfile(v); store(VAD_KEY, v); }}>
              {(Object.keys(VAD_PROFILES) as VadProfileName[]).map((k) => <option key={k} value={k}>{VAD_PROFILES[k].label}</option>)}
            </select>
          </div>
        )}
        {!ended && speech && !handsFree && (
          <button type="button" className={`call-panel__talk${talk.state === 'recording' ? ' is-on' : ''}`}
            disabled={!secure || busy || talk.state === 'recognizing' || talk.state === 'starting'}
            title={secure ? 'Сказать реплику в трубку голосом' : 'Голосовой ввод работает по https или на localhost'}
            aria-pressed={talk.state === 'recording'}
            onClick={() => { if (talk.state === 'recording') talk.stop(); else void talk.start(); }}>
            <Icon name="mic" size="sm" />
            {talk.state === 'recording' ? ` говорите… ${pad(Math.floor(talkSecs / 60))}:${pad(talkSecs % 60)} — готово`
              : talk.state === 'recognizing' ? ' распознаю…' : talk.state === 'starting' ? ' включаю микрофон…' : ' говорить'}
          </button>
        )}
      </div>
      <div className="arm-dock__section call-panel__actions">
        <span className="call-panel__switches">
          <label className="arm-switch" title="Озвучивать реплики собеседника">
            <input type="checkbox" role="switch" checked={voice} onChange={toggleVoice} />
            <span className="arm-switch__track" aria-hidden="true" />голос
          </label>
          {!ended && speech && secure && (
            <label className="arm-switch" title="Говорить без кнопки: микрофон слушает весь звонок, фразы распознаются сами">
              <input type="checkbox" role="switch" checked={handsFree} onChange={toggleHandsFree} />
              <span className="arm-switch__track" aria-hidden="true" />без рук
            </label>
          )}
        </span>
        {!ended && psy && (
          <button type="button" className="call-panel__close" title="Остановить тяжёлый учебный звонок: он не будет оценён" onClick={() => { void pause(); }}>
            пауза
          </button>
        )}
        {!ended
          ? <button type="button" className="call-panel__end" onClick={() => { void hangup(); }}><Icon name="call_end" size="sm" /> завершить</button>
          : onClose && <button type="button" className="call-panel__close" onClick={onClose}>закрыть</button>}
      </div>
    </aside>
  );
}
