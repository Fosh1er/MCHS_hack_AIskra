/** Фраза оператора → WAV для распознавания (п. 3.6, V3). Whisper работает на 16 кГц: понижаем частоту микрофона
 *  (обычно 48 кГц) усреднением — втрое меньше данных без потери разборчивости. 16 бит моно: 30 с ≈ 1 МБ. */

export function encodeWav(blocks: Float32Array[], inputRate: number, outputRate = 16_000): Blob {
  const total = blocks.reduce((n, b) => n + b.length, 0);
  const input = new Float32Array(total);
  let offset = 0;
  for (const b of blocks) { input.set(b, offset); offset += b.length; }

  const ratio = inputRate / outputRate;
  const length = Math.floor(total / ratio);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const text = (at: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, outputRate, true); view.setUint32(28, outputRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, length * 2, true);

  for (let i = 0; i < length; i++) {
    const from = Math.floor(i * ratio), to = Math.min(total, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = from; j < to; j++) sum += input[j];
    const v = Math.max(-1, Math.min(1, sum / Math.max(1, to - from)));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}
