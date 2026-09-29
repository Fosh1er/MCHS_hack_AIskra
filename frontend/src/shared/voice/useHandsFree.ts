/** Разговор без рук (п. 3.6, V3): микрофон открыт, пока режим включён; каждая фраза оператора выделяется отдельно
 *  (начало и конец — `VadDetector`) и отдаётся наружу для распознавания. Звук на сервер не течёт потоком — только
 *  готовые фразы, тем же `POST /training/speech`, что и кнопка «говорить».
 *
 *  Звук пишется непрерывно в кольцевой буфер: детектор срабатывает, когда речь уже идёт, и без «предзаписи» первое
 *  слово обрезается («Где вы находитесь?» → «вы находитесь») — так было в прототипе и так показал живой Whisper.
 *  Фраза = предзапись + речь + тишина до конца; кодируется в WAV 16 кГц (`encodeWav`). Предзапись — 0,4 с, а если
 *  оператор перебил собеседника — 0,9 с: пока тот говорит, порог выше и детектор ловит фразу на громком слове,
 *  пропуская тихое начало («Есть пострадавшие?» → «пострадавшие?» — проверено на живом Whisper).
 *
 *  Микрофон закрывается, как только режим выключен: звонок завершён, ушли со страницы, идут подсказки. */
import { useEffect, useRef, useState } from 'react';
import { VAD, VAD_PROFILES, VadDetector, rmsOf, type VadProfileName } from './vad';
import { encodeWav } from './wav';

export type HandsFreeState = 'off' | 'starting' | 'calibrating' | 'listening' | 'party' | 'hearing' | 'error';

const BLOCK = 1024; // отсчётов на кадр: ~21 мс при 48 кГц — как кадр детектора в прототипе
const PREROLL_MS = 400; // звук до срабатывания детектора, чтобы не потерять начало первого слова
const PREROLL_BARGE_IN_MS = 900; // оператор перебил собеседника: срабатывание позже, предзапись длиннее

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
    let proc: ScriptProcessorNode | null = null;
    setState('starting');

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        if (closed) { stream.getTracks().forEach((t) => t.stop()); return; }
        ctx = new AudioContext();
        await ctx.resume();
        const source = ctx.createMediaStreamSource(stream);
        // ScriptProcessorNode устарел, но работает во всех браузерах и не требует отдельного файла, как AudioWorklet
        proc = ctx.createScriptProcessor(BLOCK, 1, 1);
        const mute = ctx.createGain();
        mute.gain.value = 0; // узел должен быть подключён к выходу, иначе браузер не вызывает обработку; звук не слышен
        source.connect(proc);
        proc.connect(mute);
        mute.connect(ctx.destination);
        const rate = ctx.sampleRate;
        const blocksOf = (ms: number) => Math.ceil(((ms / 1000) * rate) / BLOCK);
        const [shortPreroll, longPreroll] = [blocksOf(PREROLL_MS), blocksOf(PREROLL_BARGE_IN_MS)];
        let partyAt = -Infinity; // когда последний раз звучал собеседник
        const vad = new VadDetector(VAD_PROFILES[profile], performance.now() + VAD.calibrationMs);
        detector.current = vad;
        setState('calibrating');

        let recent: Float32Array[] = [];
        let phrase: Float32Array[] | null = null;
        let shown: HandsFreeState = 'calibrating';
        proc.onaudioprocess = (e) => {
          if (closed) return;
          const block = new Float32Array(e.inputBuffer.getChannelData(0)); // буфер переиспользуется браузером
          const now = performance.now();
          const party = latest.current.partySpeaking();
          if (party) partyAt = now;
          const event = vad.step(rmsOf(block), now, party);
          if (phrase) phrase.push(block);
          else {
            recent.push(block);
            if (recent.length > longPreroll) recent.shift();
          }
          if (event === 'start') {
            latest.current.onSpeechStart();
            const bargeIn = now - partyAt <= VAD.echoGuardMs;
            phrase = recent.slice(-(bargeIn ? longPreroll : shortPreroll)); // предзапись вместе с текущим кадром
            recent = [];
          } else if (event === 'stop' && phrase) {
            latest.current.onPhrase(encodeWav(phrase, rate));
            phrase = null;
          }
          const next: HandsFreeState = vad.isRecording ? 'hearing' : !vad.isReady ? 'calibrating' : party ? 'party' : 'listening';
          if (next !== shown) { shown = next; setState(next); } // ~50 кадров в секунду — перерисовка только при смене
        };
      } catch {
        if (closed) return;
        setState('error');
        latest.current.onError('Нет доступа к микрофону — разрешите его в браузере');
      }
    })();

    return () => {
      closed = true;
      if (proc) { proc.onaudioprocess = null; proc.disconnect(); }
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close().catch(() => undefined);
      detector.current = null;
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps — профиль меняется на лету, без переоткрытия микрофона

  return state;
}
