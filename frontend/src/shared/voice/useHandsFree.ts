/** Разговор без рук (п. 3.6, V3): микрофон открыт, пока режим включён; каждая фраза оператора записывается отдельно
 *  (начало и конец — `VadDetector`) и отдаётся наружу для распознавания. Звук на сервер не течёт потоком — только
 *  готовые фразы, тем же `POST /training/speech`, что и кнопка «говорить».
 *
 *  Микрофон закрывается, как только режим выключен: звонок завершён, ушли со страницы, идут подсказки. */
import { useEffect, useRef, useState } from 'react';
import { VAD, VAD_PROFILES, VadDetector, rmsOf, type VadProfileName } from './vad';

export type HandsFreeState = 'off' | 'starting' | 'calibrating' | 'listening' | 'party' | 'hearing' | 'error';

const FRAME_MS = 20; // таймер, а не requestAnimationFrame: тот замирает, когда вкладка не на переднем плане

export function useHandsFree({ enabled, profile, partySpeaking, onSpeechStart, onPhrase, onError }: {
  enabled: boolean;
  profile: VadProfileName;
  partySpeaking: () => boolean;
  onSpeechStart: () => void; // оператор заговорил — перебивание: остановить голос собеседника
  onPhrase: (audio: Blob) => void;
  onError: (message: string) => void;
}): HandsFreeState {
  const [state, setState] = useState<HandsFreeState>('off');
  const latest = useRef({ partySpeaking, onSpeechStart, onPhrase, onError });
  latest.current = { partySpeaking, onSpeechStart, onPhrase, onError };
  const detector = useRef<VadDetector | null>(null);

  useEffect(() => { detector.current?.setProfile(VAD_PROFILES[profile]); }, [profile]);

  useEffect(() => {
    if (!enabled) { setState('off'); return; }
    let closed = false;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    let timer: number | undefined;
    let recorder: MediaRecorder | null = null;
    setState('starting');

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        if (closed) { stream.getTracks().forEach((t) => t.stop()); return; }
        ctx = new AudioContext();
        await ctx.resume();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        analyser.smoothingTimeConstant = 0.75;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm'].find((m) => MediaRecorder.isTypeSupported(m));
        const vad = new VadDetector(VAD_PROFILES[profile], performance.now() + VAD.calibrationMs);
        detector.current = vad;
        setState('calibrating');

        const startPhrase = (s: MediaStream) => {
          const r = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
          const chunks: Blob[] = [];
          r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
          r.onstop = () => { if (!closed && chunks.length) latest.current.onPhrase(new Blob(chunks, { type: r.mimeType || 'audio/webm' })); };
          r.start(120);
          recorder = r;
        };

        let shown: HandsFreeState = 'calibrating';
        timer = window.setInterval(() => {
          if (!stream) return;
          analyser.getByteTimeDomainData(samples);
          const party = latest.current.partySpeaking();
          const event = vad.step(rmsOf(samples), performance.now(), party);
          if (event === 'start') {
            latest.current.onSpeechStart();
            startPhrase(stream);
          } else if (event === 'stop') {
            if (recorder?.state === 'recording') recorder.stop();
            recorder = null;
          }
          const next: HandsFreeState = vad.isRecording ? 'hearing' : !vad.isReady ? 'calibrating' : party ? 'party' : 'listening';
          if (next !== shown) { shown = next; setState(next); } // 50 кадров в секунду — перерисовка только при смене
        }, FRAME_MS);
      } catch {
        if (closed) return;
        setState('error');
        latest.current.onError('Нет доступа к микрофону — разрешите его в браузере');
      }
    })();

    return () => {
      closed = true;
      window.clearInterval(timer);
      if (recorder?.state === 'recording') recorder.stop();
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close().catch(() => undefined);
      detector.current = null;
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps — профиль меняется на лету, без переоткрытия микрофона

  return state;
}
