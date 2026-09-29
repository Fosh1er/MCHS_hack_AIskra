/** Определение начала и конца фразы оператора по уровню микрофона (п. 3.6, V3 — разговор без рук).
 *
 *  Алгоритм и подобранные значения — из прототипа emotional-stt-tts: калибровка фона, адаптивный порог по шуму,
 *  старт после нескольких кадров голоса подряд, конец фразы — по устойчивой тишине. Пока звучит собеседник и сразу
 *  после, порог выше — чтобы его голос из динамиков не принять за оператора.
 *
 *  Отличие от прототипа: гистерезис работает. В прототипе порог остановки считался, но не использовался — фраза
 *  рвалась на тихом слоге. Здесь фраза продолжается, пока уровень выше порога остановки (он ниже порога старта).
 *
 *  Модуль без DOM и Web Audio: на вход — уровень (RMS) и время, на выход — событие. Так его легко проверить. */

export type VadProfileName = 'high' | 'balanced' | 'strict';

export interface VadProfile {
  label: string;
  startFrames: number; // кадров голоса подряд до начала фразы
  startNoiseMultiplier: number;
  startOffset: number;
  absoluteStartFloor: number; // порог старта не ниже этого, даже в очень тихой комнате
  partyMultiplier: number; // во сколько раз выше порог, пока говорит собеседник
  partyExtraFrames: number;
}

export const VAD_PROFILES: Record<VadProfileName, VadProfile> = {
  high: { label: 'высокая — слышит тихую речь', startFrames: 3, startNoiseMultiplier: 2.1, startOffset: 0.011, absoluteStartFloor: 0.032, partyMultiplier: 1.45, partyExtraFrames: 4 },
  balanced: { label: 'сбалансированная', startFrames: 4, startNoiseMultiplier: 2.4, startOffset: 0.014, absoluteStartFloor: 0.038, partyMultiplier: 1.55, partyExtraFrames: 6 },
  strict: { label: 'строгая — меньше реагирует на шум', startFrames: 5, startNoiseMultiplier: 2.8, startOffset: 0.018, absoluteStartFloor: 0.045, partyMultiplier: 1.7, partyExtraFrames: 8 },
};

export const VAD = {
  calibrationMs: 900, // слушаем фон, пока оператор молчит
  startCooldownMs: 650, // пауза между фразами
  minSpeechMs: 420, // короче — не фраза, а щелчок
  silenceMs: 680, // столько тишины — конец фразы
  maxSpeechMs: 30_000, // реплика в трубку — не дольше 30 с
  echoGuardMs: 900, // после реплики собеседника порог ещё повышен
  stopNoiseMultiplier: 1.25,
  stopOffset: 0.007,
  noiseFollow: 0.005, // шум подстраивается медленно и только в тишине
};

export type VadEvent = 'calibrated' | 'start' | 'stop' | null;

export class VadDetector {
  private noise = 0.008;
  private ready = false;
  private recording = false;
  private candidate = 0;
  private startedAt = 0;
  private lastVoiceAt = 0;
  private lastEndedAt = 0;
  private guardUntil = 0;
  private partyWasSpeaking = false;

  constructor(private profile: VadProfile, private readonly calibrateUntil: number) {}

  get isRecording(): boolean { return this.recording; }
  get isReady(): boolean { return this.ready; }
  setProfile(profile: VadProfile): void { this.profile = profile; }

  /** Один кадр (~20 мс): `rms` — уровень 0…1, `partySpeaking` — звучит ли сейчас собеседник. */
  step(rms: number, now: number, partySpeaking: boolean): VadEvent {
    const p = this.profile;
    if (this.partyWasSpeaking && !partySpeaking) this.guardUntil = now + VAD.echoGuardMs;
    this.partyWasSpeaking = partySpeaking;

    if (!this.ready) {
      this.noise = this.noise * 0.85 + rms * 0.15;
      if (now < this.calibrateUntil) return null;
      this.ready = true;
      this.lastEndedAt = now;
      return 'calibrated';
    }

    if (this.recording) {
      const stopThreshold = Math.max(p.absoluteStartFloor * 0.62, this.noise * VAD.stopNoiseMultiplier + VAD.stopOffset);
      if (rms >= stopThreshold) this.lastVoiceAt = now;
      const silent = now - this.lastVoiceAt > VAD.silenceMs && now - this.startedAt > VAD.minSpeechMs;
      if (silent || now - this.startedAt > VAD.maxSpeechMs) {
        this.recording = false;
        this.candidate = 0;
        this.lastEndedAt = now;
        return 'stop';
      }
      return null;
    }

    const echo = partySpeaking || now < this.guardUntil;
    const base = Math.max(p.absoluteStartFloor, this.noise * p.startNoiseMultiplier + p.startOffset);
    const threshold = echo ? Math.max(base * p.partyMultiplier, base + 0.025) : base;
    const frames = p.startFrames + (echo ? p.partyExtraFrames : 0);
    if (rms >= threshold) {
      this.candidate += 1;
      if (this.candidate >= frames && now - this.lastEndedAt >= VAD.startCooldownMs) {
        this.recording = true;
        this.startedAt = now;
        this.lastVoiceAt = now;
        return 'start';
      }
    } else {
      this.candidate = Math.max(0, this.candidate - 1);
      if (!echo) this.noise = this.noise * (1 - VAD.noiseFollow) + rms * VAD.noiseFollow;
    }
    return null;
  }
}

/** Уровень сигнала кадра: среднеквадратичное значение отсчётов −1…1. */
export function rmsOf(samples: Float32Array): number {
  let sum = 0;
  for (const v of samples) sum += v * v;
  return Math.sqrt(sum / samples.length);
}

const words = (text: string) => new Set(
  text.toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]+/gu, ' ').split(/\s+/).filter((w) => w.length >= 3),
);

/** Распознанная «фраза оператора» — на деле эхо собеседника из динамиков: ≥ 65 % слов из его последней реплики,
 *  прозвучавшей не раньше 8 с назад. */
export function isLikelyEcho(text: string, lastParty: { text: string; at: number } | null, now: number): boolean {
  if (!lastParty || now - lastParty.at > 8_000 || text.trim().length < 8) return false;
  const heard = words(text);
  const said = words(lastParty.text);
  if (heard.size < 3 || said.size < 3) return false;
  let overlap = 0;
  for (const w of heard) if (said.has(w)) overlap += 1;
  return overlap / heard.size >= 0.65;
}
