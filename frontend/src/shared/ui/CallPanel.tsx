/** Панель разговора (п. 1.4, 2.3): реплики оператора и ИИ-собеседника, таймер, «завершить».
 *  Голос (P1): реплики собеседника озвучиваются синтезом речи браузера (Web Speech API работает офлайн на ОС
 *  с русским голосом); оператор говорит в микрофон — запись распознаёт Whisper на сервере (`POST /training/speech`),
 *  либо печатает. Вид — тёмный док АРМ (ui-kit: Transcript, Composer).
 *  Эмоции (п. 3.6): у реплики заявителя — его состояние; голос следует ему темпом, высотой и громкостью,
 *  а в тексте состояние видно подписью у реплики — в текстовом режиме это единственный канал интонации.
 *  Если на сервере настроен синтез (`GET /training/speech` → `tts`), реплика звучит голосом модели с эмоцией;
 *  сбой синтеза — та же реплика голосом браузера. */
import { useEffect, useRef, useState } from 'react';
import { Composer, Icon, Transcript, type TranscriptMessage } from '@smena112/ui-kit';
import { endCall, getCall, replicaAudioUrl, sendReplica, transcribe, useSpeechStatus, type CallMessage, type Tone } from '../api/training';

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
  const [messages, setMessages] = useState<CallMessage[]>(initial ?? []);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState('');
  const [startedAt, setStartedAt] = useState<number>(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [voice, setVoice] = useState(() => { try { return localStorage.getItem(VOICE_KEY) === '1'; } catch { return false; } });
  const spoken = useRef(0);
  const audio = useRef<HTMLAudioElement | null>(null);
  const status = useSpeechStatus();
  const serverVoice = status.data?.tts ?? false;

  const stopVoice = () => {
    audio.current?.pause();
    audio.current = null;
    try { window.speechSynthesis?.cancel(); } catch { /* нет синтеза */ }
  };
  /** Реплика собеседника: серверный голос с эмоцией, при сбое — голос браузера. */
  const play = (m: CallMessage) => {
    stopVoice();
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

  useEffect(() => {
    getCall(callId).then((c) => {
      setMessages(c.messages);
      setStartedAt(new Date(c.answered_at ?? c.started_at).getTime());
      setEnded(c.status === 'ended');
    }).catch(() => undefined);
  }, [callId]);
  useEffect(() => { if (ended) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, [ended]);
  useEffect(() => {
    if (status.isLoading) return; // сначала узнаём, есть ли серверный голос, — иначе первую реплику скажет браузер
    const party = messages.filter((m) => m.speaker === 'party');
    if (voice && party.length > spoken.current) play(party[party.length - 1]);
    spoken.current = party.length;
  }, [messages, voice, status.isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (spoken?: string) => {
    const t = (spoken ?? text).trim();
    if (!t || busy || ended) return;
    if (spoken === undefined) setText('');
    setBusy(true);
    setError('');
    const at = new Date().toISOString();
    setMessages((m) => [...m, { speaker: 'operator', text: t, at }]);
    try {
      const r = await sendReplica(callId, t);
      setMessages((m) => [...m, { speaker: r.speaker, text: r.text, at: new Date().toISOString(), id: r.message_id, tone: r.tone }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const hangup = async () => {
    if (!ended) await endCall(callId).catch(() => undefined);
    stopVoice();
    setEnded(true);
    onEnded?.();
  };
  const speech = status.data?.enabled ?? false;
  const secure = typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices;
  const talk = useTalk((t) => { setError(''); void send(t); }, setError);
  const talkSecs = talk.state === 'recording' ? Math.floor((now - talk.since) / 1000) : 0;
  const toggleVoice = () => {
    const v = !voice;
    if (!v) stopVoice();
    setVoice(v);
    try { localStorage.setItem(VOICE_KEY, v ? '1' : '0'); } catch { /* приватный режим */ }
  };

  const secs = Math.max(0, Math.floor(((ended ? now : now) - startedAt) / 1000));
  const transcript: TranscriptMessage[] = messages.map((m) => ({
    from: m.speaker === 'operator' ? 'me' : m.speaker === 'party' ? 'them' : 'sys',
    who: m.speaker === 'operator' ? 'Вы' : m.tone ? `${partyName} · ${m.tone.emotion_title}` : partyName,
    text: m.text,
  }));
  if (busy) transcript.push({ from: 'sys', text: `${partyName} отвечает…` });

  return (
    <aside className="call-panel arm-dock" aria-label={`Разговор: ${title}`}>
      <div className="arm-dock__section">
        <div className="arm-dock__title">
          <span><Icon name="phone" size="sm" /> {title}</span>
          <span className="call-panel__timer" aria-label="Длительность разговора">{ended ? 'завершён' : `${pad(Math.floor(secs / 60))}:${pad(secs % 60)}`}</span>
        </div>
        {subtitle && <div className="call-panel__sub">{subtitle}</div>}
      </div>
      <div className="arm-dock__section arm-dock__section--grow">
        <Transcript messages={transcript} />
        {error && <div className="call-panel__err" role="alert">{error}</div>}
        {!ended && <Composer value={text} onChange={setText} onSend={() => { void send(); }} />}
        {!ended && speech && (
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
        <label className="arm-switch" title="Озвучивать реплики собеседника">
          <input type="checkbox" role="switch" checked={voice} onChange={toggleVoice} />
          <span className="arm-switch__track" aria-hidden="true" />голос
        </label>
        {!ended
          ? <button type="button" className="call-panel__end" onClick={() => { void hangup(); }}><Icon name="call_end" size="sm" /> завершить</button>
          : onClose && <button type="button" className="call-panel__close" onClick={onClose}>закрыть</button>}
      </div>
    </aside>
  );
}
