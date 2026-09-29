const elements = {
  start: document.querySelector("#start-button"),
  stop: document.querySelector("#stop-button"),
  ttsTest: document.querySelector("#tts-test-button"),
  clear: document.querySelector("#clear-button"),
  language: document.querySelector("#language-select"),
  vadSensitivity: document.querySelector("#vad-sensitivity-select"),
  voice: document.querySelector("#voice-select"),
  emotion: document.querySelector("#emotion-select"),
  transcript: document.querySelector("#transcript"),
  empty: document.querySelector("#empty-state"),
  orb: document.querySelector("#orb"),
  orbCaption: document.querySelector("#orb-caption"),
  connectionPill: document.querySelector("#connection-pill"),
  connectionLabel: document.querySelector("#connection-label"),
  latency: document.querySelector("#latency-label"),
  scenario: document.querySelector("#scenario-select"),
  toneStatus: document.querySelector("#tone-status"),
  toneNotation: document.querySelector("#tone-notation"),
};

const scenarioDefinitions = {
  medical: {
    label: "Медицинский кризис",
    situation: "Звонящий сообщает о сильной боли в груди у взрослого человека дома. Человеку становится хуже.",
    caller: "взволнованный родственник",
    facts: "Точный адрес нужно назвать после прямого вопроса оператора. Дыхание есть, сознание сохранено.",
    initialTone: { emotion: "fear", intensity: 8, pace: "fast", volume: "loud", urgency: "critical", trust: 3, cooperation: 5, breathing: "rapid", interruptions: "frequent" },
  },
  domestic: {
    label: "Домашний конфликт",
    situation: "Звонящий заперся в комнате после крика и ударов. Агрессивный человек всё ещё находится в квартире.",
    caller: "испуганный взрослый",
    facts: "Звонящий старается говорить тихо. В квартире есть ещё один человек; оружие не подтверждено.",
    initialTone: { emotion: "fear", intensity: 8, pace: "fast", volume: "whisper", urgency: "critical", trust: 2, cooperation: 4, breathing: "rapid", interruptions: "occasional" },
  },
  crash: {
    label: "ДТП с пострадавшим",
    situation: "Звонящий стал свидетелем ДТП. В одной машине человек жалуется на боль и не может самостоятельно выйти.",
    caller: "очевидец аварии",
    facts: "Звонящий находится рядом с машиной, вокруг движется транспорт. Количество пострадавших нужно уточнить.",
    initialTone: { emotion: "shock", intensity: 7, pace: "fast", volume: "loud", urgency: "high", trust: 4, cooperation: 6, breathing: "irregular", interruptions: "occasional" },
  },
  fire: {
    label: "Пожар в помещении",
    situation: "Звонящий видит дым и огонь в квартире. Он вышел в подъезд, но не уверен, успели ли выйти соседи.",
    caller: "испуганный жилец",
    facts: "Есть густой дым; этаж и точный адрес нужно получить вопросами оператора. Нельзя выдумывать количество людей.",
    initialTone: { emotion: "panic", intensity: 9, pace: "very_fast", volume: "shouting", urgency: "critical", trust: 3, cooperation: 5, breathing: "rapid", interruptions: "frequent" },
  },
  missingChild: {
    label: "Пропавший ребёнок",
    situation: "Родитель потерял ребёнка в людном месте несколько минут назад и не может его найти.",
    caller: "растерянный родитель",
    facts: "Родитель помнит одежду ребёнка, но сначала говорит обрывками. Детали нужно раскрывать по вопросам.",
    initialTone: { emotion: "grief", intensity: 8, pace: "fast", volume: "loud", urgency: "critical", trust: 3, cooperation: 5, breathing: "rapid", interruptions: "frequent" },
  },
};

const toneRanges = {
  emotion: new Set(["calm", "relief", "fear", "panic", "shock", "anger", "grief", "confusion", "pain"]),
  pace: new Set(["very_slow", "slow", "normal", "fast", "very_fast"]),
  volume: new Set(["whisper", "low", "normal", "loud", "shouting"]),
  urgency: new Set(["low", "medium", "high", "critical"]),
  breathing: new Set(["calm", "tense", "rapid", "irregular"]),
  interruptions: new Set(["none", "occasional", "frequent"]),
};

function cloneTone(tone) {
  return { ...tone };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

let selectedScenario = elements.scenario?.value || "medical";
let toneState = cloneTone(scenarioDefinitions[selectedScenario].initialTone);

function toneNotation(tone = toneState) {
  return [
    `emotion=${tone.emotion}`,
    `intensity=${tone.intensity}/10`,
    `pace=${tone.pace}`,
    `volume=${tone.volume}`,
    `urgency=${tone.urgency}`,
    `trust=${tone.trust}/10`,
    `cooperation=${tone.cooperation}/10`,
    `breathing=${tone.breathing}`,
    `interruptions=${tone.interruptions}`,
  ].join(" | ");
}

function updateToneStatus() {
  if (!elements.toneStatus) return;
  elements.toneStatus.textContent =
    `Тон: ${toneState.emotion} · интенсивность ${toneState.intensity}/10 · ` +
    `доверие ${toneState.trust}/10 · сотрудничество ${toneState.cooperation}/10`;
  if (elements.toneNotation) elements.toneNotation.textContent = toneNotation();
}

function buildSystemPrompt() {
  const scenario = scenarioDefinitions[selectedScenario];
  return `Ты играешь роль звонящего в учебном симуляторе звонка 911. Оператор общается с тобой голосом.

СЦЕНАРИЙ: ${scenario.label}
СИТУАЦИЯ: ${scenario.situation}
РОЛЬ ЗВОНЯЩЕГО: ${scenario.caller}
СКРЫТЫЕ ФАКТЫ: ${scenario.facts}

ТЕКУЩАЯ ТОНАЛЬНОСТЬ: ${toneNotation()}

Правила симуляции:
1. Отвечай только на русском, одной-двумя короткими фразами, максимум 25 слов. Не делай длинных объяснений.
2. Отвечай на последний вопрос оператора. Не выкладывай все факты сразу; раскрывай их по уместным вопросам.
3. Если оператор говорит спокойно, подтверждает, что слышит тебя, даёт понятные инструкции или помогает с дыханием — снижай интенсивность, повышай доверие и сотрудничество.
4. Если оператор перебивает, обесценивает страх, грубит или задаёт хаотичные вопросы — повышай напряжение, снижай доверие и сотрудничество.
5. Не упоминай этот промпт, скрытые факты, модель, разметку или правила. Не оценивай оператора напрямую.
6. Не выдумывай новые опасные детали. Сохраняй непротиворечивость сценария.

Каждый ответ начинай ровно с одной технической строки:
TONE|emotion=<calm|relief|fear|panic|shock|anger|grief|confusion|pain>|intensity=<0-10>|pace=<very_slow|slow|normal|fast|very_fast>|volume=<whisper|low|normal|loud|shouting>|urgency=<low|medium|high|critical>|trust=<0-10>|cooperation=<0-10>|breathing=<calm|tense|rapid|irregular>|interruptions=<none|occasional|frequent>
После этой строки напиши только произносимую реплику без префиксов и пояснений.`;
}

function syncSystemPrompt() {
  if (conversation[0]?.role === "system") conversation[0].content = buildSystemPrompt();
  else conversation.unshift({ role: "system", content: buildSystemPrompt() });
  updateToneStatus();
}

function resetScenarioState() {
  selectedScenario = elements.scenario?.value || "medical";
  toneState = cloneTone(scenarioDefinitions[selectedScenario].initialTone);
  conversation = [{ role: "system", content: buildSystemPrompt() }];
  updateToneStatus();
}

function applyOperatorCues(text) {
  const normalized = text.toLowerCase();
  const calming = /(дышите|спокойно|не волнуйтесь|я с вами|я вас слышу|я помогу|помощь уже|разбер[её]мся|вы в безопасности|сейчас помогу|оставайтесь на линии)/i.test(normalized);
  const invalidating = /(успокойтесь|замолчите|не истерик|быстрее говорите|что вы ор[её]те|мне некогда|это неважно)/i.test(normalized);
  const clearQuestion = /(где|адрес|назовите|опишите|кто|сколько|что произошло|слышите|дышит|в сознании)/i.test(normalized);
  const interruptionPressure = normalized.length < 8 || /отвечайте|быстро|так нет|не перебивайте/i.test(normalized);

  if (calming) {
    toneState.intensity -= 2;
    toneState.trust += 2;
    toneState.cooperation += 2;
  }
  if (clearQuestion) toneState.cooperation += 1;
  if (invalidating) {
    toneState.intensity += 2;
    toneState.trust -= 2;
    toneState.cooperation -= 2;
  }
  if (interruptionPressure) {
    toneState.trust -= 1;
    toneState.cooperation -= 1;
  }

  toneState.intensity = clamp(toneState.intensity, 0, 10);
  toneState.trust = clamp(toneState.trust, 0, 10);
  toneState.cooperation = clamp(toneState.cooperation, 0, 10);

  if (toneState.intensity <= 3) {
    toneState.emotion = "relief";
    toneState.pace = "slow";
    toneState.volume = "low";
    toneState.breathing = "calm";
    toneState.interruptions = "none";
  } else if (toneState.intensity <= 5) {
    toneState.pace = "normal";
    toneState.volume = "normal";
    toneState.breathing = "tense";
    toneState.interruptions = "occasional";
  } else if (toneState.intensity >= 8) {
    toneState.pace = toneState.emotion === "panic" ? "very_fast" : "fast";
    toneState.volume = toneState.emotion === "fear" && selectedScenario === "domestic" ? "whisper" : "loud";
    toneState.breathing = "rapid";
    toneState.interruptions = "frequent";
  }

  syncSystemPrompt();
}

function applyToneHeader(header) {
  const fields = header.replace(/^TONE\|?/, "").split(/[|;]/).map((part) => part.trim()).filter(Boolean);
  for (const field of fields) {
    const separator = field.indexOf("=");
    if (separator < 0) continue;
    const key = field.slice(0, separator).trim();
    const value = field.slice(separator + 1).trim().replace(/\/10$/, "");
    if (["intensity", "trust", "cooperation"].includes(key)) {
      const number = Number.parseInt(value, 10);
      if (Number.isFinite(number)) toneState[key] = clamp(number, 0, 10);
    } else if (key === "urgency" && /^\d+$/.test(value)) {
      const number = Number(value);
      toneState.urgency = number >= 9 ? "critical" : number >= 6 ? "high" : number >= 3 ? "medium" : "low";
    } else if (key === "breathing" && value === "heavy") {
      toneState.breathing = "rapid";
    } else if (toneRanges[key]?.has(value)) {
      toneState[key] = value;
    }
  }
  updateToneStatus();
}

function toneToTtsDirective(tone) {
  return `(speak in Russian with ${tone.emotion} emotion; intensity ${tone.intensity} out of 10; ${tone.pace} pace; ${tone.volume} volume; ${tone.urgency} urgency; ${tone.breathing} breathing; trust ${tone.trust} out of 10; cooperation ${tone.cooperation} out of 10)`;
}

let microphoneStream = null;
let audioContext = null;
let analyser = null;
let microphoneSource = null;
let monitorFrame = null;
let recorder = null;
let recordedChunks = [];
let speechStartedAt = 0;
let lastVoiceAt = 0;
let active = false;
let stopping = false;
let processingTurn = false;
let noiseFloor = 0.008;
let noiseCalibrationUntil = 0;
let vadReady = false;
let speechCandidateFrames = 0;
let lastSpeechEndedAt = 0;

const VAD = {
  calibrationMs: 900,
  startCooldownMs: 650,
  minSpeechMs: 420,
  silenceMs: 680,
  stopNoiseMultiplier: 1.25,
  stopOffset: 0.007,
};

const VAD_PROFILES = {
  high: {
    label: "Высокая — слышит тихую речь",
    startFrames: 3,
    startNoiseMultiplier: 2.1,
    startOffset: 0.011,
    absoluteStartFloor: 0.032,
    ttsMultiplier: 1.45,
    ttsExtraFrames: 4,
  },
  balanced: {
    label: "Сбалансированная",
    startFrames: 4,
    startNoiseMultiplier: 2.4,
    startOffset: 0.014,
    absoluteStartFloor: 0.038,
    ttsMultiplier: 1.55,
    ttsExtraFrames: 6,
  },
  strict: {
    label: "Строгая — меньше реакции на шум",
    startFrames: 5,
    startNoiseMultiplier: 2.8,
    startOffset: 0.018,
    absoluteStartFloor: 0.045,
    ttsMultiplier: 1.7,
    ttsExtraFrames: 8,
  },
};

function currentVadProfile() {
  return VAD_PROFILES[elements.vadSensitivity?.value] || VAD_PROFILES.high;
}

function restoreVadProfile() {
  if (!elements.vadSensitivity) return;
  try {
    const saved = window.localStorage.getItem("voice-agent-vad-sensitivity");
    if (saved && VAD_PROFILES[saved]) elements.vadSensitivity.value = saved;
  } catch {
    // Local storage can be unavailable in private browser contexts.
  }
}

function persistVadProfile() {
  if (!elements.vadSensitivity) return;
  try {
    window.localStorage.setItem("voice-agent-vad-sensitivity", elements.vadSensitivity.value);
  } catch {
    // Local storage can be unavailable in private browser contexts.
  }
}

let conversation = [{ role: "system", content: buildSystemPrompt() }];
let activeUserMessage = null;
let activeAgentMessage = null;
let chatAbortController = null;

let speechGeneration = 0;
let ttsQueue = [];
let ttsBuffer = "";
let ttsAbortController = null;
let currentAudio = null;
let ttsRequestActive = false;
let ttsGuardUntil = 0;
let lastSpokenText = "";
let lastSpokenAt = 0;

const ECHO_GUARD_MS = 900;
const ECHO_MATCH_WINDOW_MS = 8000;

function setStatus(label, mode = "offline") {
  elements.connectionLabel.textContent = label;
  elements.connectionPill.className = `status-pill ${mode}`;
}

function setOrb(mode, caption) {
  elements.orb.className = `orb ${mode}`;
  elements.orbCaption.textContent = caption;
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  elements.latency.textContent = message;
  setStatus("Ошибка", "offline");
  setOrb("idle", "Нужна проверка настроек");
  console.error(error);
  window.alert(message);
}

function resetActiveMessages() {
  activeUserMessage = null;
  activeAgentMessage = null;
}

function createMessage(role) {
  elements.empty.hidden = true;
  const message = document.createElement("article");
  message.className = `message ${role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = role === "user" ? "Вы" : "Агент";

  const text = document.createElement("div");
  text.className = "message-text";
  message.append(meta, text);
  elements.transcript.append(message);
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
  return { message, text };
}

function appendMessage(role, delta) {
  const activeMessage = role === "user" ? activeUserMessage : activeAgentMessage;
  const current = activeMessage ?? createMessage(role);
  current.text.textContent += delta;
  if (role === "user") activeUserMessage = current;
  else activeAgentMessage = current;
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
}

function finishUserMessage() {
  activeUserMessage = null;
}

function finishAgentMessage() {
  activeAgentMessage = null;
}

function supportedRecorderOptions() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  const mimeType = candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));
  return mimeType ? { mimeType } : {};
}

function formatFromMime(mimeType = "audio/webm") {
  const container = mimeType.split(";")[0].split("/")[1] || "webm";
  return container === "x-m4a" ? "m4a" : container;
}

function normalizedWords(text) {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .split(/\s+/)
      .filter((word) => word.length >= 3),
  );
}

function isLikelyTtsEcho(text) {
  if (!lastSpokenText || performance.now() - lastSpokenAt > ECHO_MATCH_WINDOW_MS || text.trim().length < 8) return false;
  const transcriptWords = normalizedWords(text);
  const spokenWords = normalizedWords(lastSpokenText);
  if (transcriptWords.size < 3 || spokenWords.size < 3) return false;

  let overlap = 0;
  for (const word of transcriptWords) {
    if (spokenWords.has(word)) overlap += 1;
  }
  return overlap / transcriptWords.size >= 0.65;
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function stopSpeaking() {
  speechGeneration += 1;
  ttsQueue = [];
  ttsBuffer = "";
  ttsAbortController?.abort();
  ttsAbortController = null;

  const hadAudio = Boolean(currentAudio);
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.removeAttribute("src");
    currentAudio.load();
    currentAudio = null;
  }
  if (hadAudio) ttsGuardUntil = performance.now() + 350;
}

function queueSpeech(text, generation, tone = toneState) {
  const cleanText = text.replace(/\s+/g, " ").trim();
  if (!cleanText || generation !== speechGeneration) return;
  const toneSnapshot = cloneTone(tone);
  if (elements.emotion?.value && elements.emotion.value !== "adaptive") {
    toneSnapshot.emotion = elements.emotion.value;
  }
  ttsQueue.push({ text: cleanText, generation, tone: toneSnapshot });
  playNextSpeech();
}

async function playNextSpeech() {
  if (currentAudio || ttsRequestActive || ttsQueue.length === 0) return;

  const item = ttsQueue.shift();
  if (!item || item.generation !== speechGeneration) return playNextSpeech();

  ttsRequestActive = true;
  ttsAbortController = new AbortController();
  try {
    const response = await fetch("/api/v1/training/voice-lab/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        input: `${toneToTtsDirective(item.tone)} ${item.text}`,
        voice: elements.voice?.value || "Zephyr",
      }),
      signal: ttsAbortController.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.details || payload.error || "TTS request failed.");
    }

    const blob = await response.blob();
    if (item.generation !== speechGeneration) return;

    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    lastSpokenText = item.text;
    lastSpokenAt = performance.now();
    setOrb("speaking", "Агент говорит");
    setStatus("Говорит", "online");

    const cleanup = () => {
      URL.revokeObjectURL(url);
      audio.removeAttribute("src");
      audio.load();
      if (currentAudio === audio) {
        currentAudio = null;
        ttsGuardUntil = performance.now() + ECHO_GUARD_MS;
      }
    };

    audio.addEventListener("ended", () => {
      cleanup();
      playNextSpeech();
      if (!currentAudio && ttsQueue.length === 0 && !recorder) {
        setOrb("idle", "Готов слушать");
        setStatus("Подключён", "online");
      }
    }, { once: true });
    audio.addEventListener("error", () => {
      cleanup();
      elements.latency.textContent = "Не удалось воспроизвести TTS-аудио";
      playNextSpeech();
    }, { once: true });

    await audio.play();
  } catch (error) {
    if (error.name !== "AbortError") showError(error);
  } finally {
    ttsRequestActive = false;
    ttsAbortController = null;
  }
}

function feedSpeechText(delta, generation) {
  if (generation !== speechGeneration) return;
  ttsBuffer += delta;
}

function flushSpeechText(generation) {
  if (generation !== speechGeneration) return;
  queueSpeech(ttsBuffer, generation, toneState);
  ttsBuffer = "";
}

function extractDelta(payload) {
  const content = payload?.choices?.[0]?.delta?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((item) => (typeof item === "string" ? item : item?.text || "")).join("");
  }
  return "";
}

async function consumeChatStream(response, generation) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assistantText = "";
  let protocolBuffer = "";
  let toneHeaderHandled = false;

  const visibleDelta = (delta) => {
    if (toneHeaderHandled) return delta;
    protocolBuffer += delta;
    const headerMatch = protocolBuffer.match(/^TONE\|[\s\S]*?interruptions=[^|\n]+(?:\||\n)/i);
    if (!headerMatch) return "";

    const headerToken = headerMatch[0];
    const header = headerToken.replace(/[|\n]$/, "").trim();
    const remainder = protocolBuffer.slice(headerToken.length);
    toneHeaderHandled = true;
    if (header.startsWith("TONE|")) applyToneHeader(header);
    else return headerToken + remainder;
    protocolBuffer = "";
    return remainder;
  };

  const handleLine = (line) => {
    if (!line.startsWith("data:")) return;
    const raw = line.slice(5).trim();
    if (!raw || raw === "[DONE]") return;

    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }

    const delta = extractDelta(payload);
    if (!delta || generation !== speechGeneration) return;
    const speechDelta = visibleDelta(delta);
    if (!speechDelta) return;
    assistantText += speechDelta;
    appendMessage("agent", speechDelta);
    feedSpeechText(speechDelta, generation);
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    lines.forEach(handleLine);
    if (done) break;
  }

  if (generation === speechGeneration) {
    if (!toneHeaderHandled && protocolBuffer) {
      assistantText += protocolBuffer;
      appendMessage("agent", protocolBuffer);
      feedSpeechText(protocolBuffer, generation);
    }
    flushSpeechText(generation);
    finishAgentMessage();
    if (assistantText) conversation.push({ role: "assistant", content: assistantText });
  }
}

async function askAgent(userText) {
  const generation = speechGeneration;
  syncSystemPrompt();
  processingTurn = true;
  setStatus("Думает", "online");
  setOrb("idle", "Агент формирует ответ…");
  ttsBuffer = "";
  chatAbortController = new AbortController();

  try {
    const response = await fetch("/api/v1/training/voice-lab/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ messages: conversation }),
      signal: chatAbortController.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.details || payload.error || "Chat request failed.");
    }

    await consumeChatStream(response, generation);
  } catch (error) {
    if (error.name !== "AbortError") showError(error);
  } finally {
    chatAbortController = null;
    processingTurn = false;
    if (active && !recorder && !currentAudio) {
      setStatus("Подключён", "online");
      setOrb("idle", "Готов слушать");
    }
  }
}

async function transcribeAndRespond(blob, mimeType) {
  if (stopping || !active || blob.size === 0) return;
  processingTurn = true;
  setStatus("Распознаёт", "online");
  setOrb("idle", "Перевожу речь в текст…");

  try {
    const response = await fetch("/api/v1/training/voice-lab/stt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        audio: arrayBufferToBase64(await blob.arrayBuffer()),
        format: formatFromMime(mimeType),
        language: elements.language.value,
      }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.details || payload.error || "STT request failed.");
    }

    const payload = await response.json();
    const text = String(payload.text || "").trim();
    if (!text) return;
    if (isLikelyTtsEcho(text)) {
      elements.latency.textContent = "Фоновое эхо TTS отброшено";
      return;
    }

    appendMessage("user", text);
    finishUserMessage();
    applyOperatorCues(text);
    conversation.push({ role: "user", content: text });
    await askAgent(text);
  } catch (error) {
    showError(error);
  } finally {
    processingTurn = false;
    if (active && !recorder && !currentAudio) {
      setStatus("Подключён", "online");
      setOrb("idle", "Готов слушать");
    }
  }
}

function startRecording() {
  if (!active || recorder || stopping) return;

  stopSpeaking();
  chatAbortController?.abort();
  activeAgentMessage = null;
  speechCandidateFrames = 0;
  recordedChunks = [];
  speechStartedAt = performance.now();
  lastVoiceAt = speechStartedAt;
  setStatus("Слушает", "online");
  setOrb("listening", "Слушаю вас");

  try {
    recorder = new MediaRecorder(microphoneStream, supportedRecorderOptions());
    const mimeType = recorder.mimeType || "audio/webm";
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      const blob = new Blob(recordedChunks, { type: mimeType });
      recorder = null;
      recordedChunks = [];
      transcribeAndRespond(blob, mimeType);
    }, { once: true });
    recorder.start(120);
  } catch (error) {
    recorder = null;
    showError(error);
  }
}

function stopRecording() {
  if (!recorder || recorder.state === "inactive") return;
  recorder.stop();
}

function monitorMicrophone() {
  if (!active || !analyser) return;

  const vadProfile = currentVadProfile();

  const samples = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(samples);
  let sum = 0;
  for (const sample of samples) {
    const normalized = (sample - 128) / 128;
    sum += normalized * normalized;
  }
  const rms = Math.sqrt(sum / samples.length);
  const now = performance.now();

  if (!vadReady) {
    noiseFloor = noiseFloor * 0.85 + rms * 0.15;
    if (now < noiseCalibrationUntil) {
      setStatus("Калибрую микрофон", "online");
      setOrb("idle", "Слушаю фон, пока не говорите");
      monitorFrame = requestAnimationFrame(monitorMicrophone);
      return;
    }
    vadReady = true;
    lastSpeechEndedAt = now;
    setStatus("Подключён", "online");
    setOrb("idle", "Готов слушать");
  }

  const startThreshold = Math.max(
    vadProfile.absoluteStartFloor,
    noiseFloor * vadProfile.startNoiseMultiplier + vadProfile.startOffset,
  );
  const stopThreshold = Math.max(
    vadProfile.absoluteStartFloor * 0.62,
    noiseFloor * VAD.stopNoiseMultiplier + VAD.stopOffset,
  );
  const ttsActive = Boolean(currentAudio) || now < ttsGuardUntil;
  const activeStartThreshold = ttsActive
    ? Math.max(startThreshold * vadProfile.ttsMultiplier, startThreshold + 0.025)
    : startThreshold;
  const requiredStartFrames = ttsActive
    ? vadProfile.startFrames + vadProfile.ttsExtraFrames
    : vadProfile.startFrames;

  if (rms >= activeStartThreshold) {
    speechCandidateFrames += 1;
    if (recorder) {
      lastVoiceAt = now;
    } else if (
      speechCandidateFrames >= requiredStartFrames &&
      now - lastSpeechEndedAt >= VAD.startCooldownMs
    ) {
      lastVoiceAt = now;
      startRecording();
    }
  } else {
    speechCandidateFrames = Math.max(0, speechCandidateFrames - 1);

    if (!recorder && !ttsActive) {
      // Slowly follow changes in room noise, but never learn while speech is active.
      noiseFloor = noiseFloor * 0.995 + rms * 0.005;
    } else if (
      now - lastVoiceAt > VAD.silenceMs &&
      now - speechStartedAt > VAD.minSpeechMs
    ) {
      lastSpeechEndedAt = now;
      stopRecording();
    }
  }

  monitorFrame = requestAnimationFrame(monitorMicrophone);
}

async function startConversation() {
  elements.start.disabled = true;
  elements.language.disabled = true;
  elements.vadSensitivity.disabled = true;
  elements.scenario.disabled = true;
  elements.emotion.disabled = true;
  elements.voice.disabled = true;
  resetScenarioState();
  stopping = false;
  vadReady = false;
  noiseFloor = 0.008;
  noiseCalibrationUntil = performance.now() + VAD.calibrationMs;
  speechCandidateFrames = 0;
  setStatus("Запрашиваю микрофон…", "offline");
  setOrb("listening", "Разрешите доступ к микрофону");

  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Браузер не поддерживает доступ к микрофону.");
    }
    if (!window.MediaRecorder) {
      throw new Error("Браузер не поддерживает MediaRecorder.");
    }

    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    audioContext = new AudioContext();
    await audioContext.resume();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.75;
    microphoneSource = audioContext.createMediaStreamSource(microphoneStream);
    microphoneSource.connect(analyser);
    active = true;
    setStatus("Подключён", "online");
    setOrb("idle", "Готов слушать");
    elements.latency.textContent = "Микрофон активен · VAD включён";
    monitorMicrophone();
    elements.stop.disabled = false;
  } catch (error) {
    stopConversation();
    showError(error);
  }
}

function stopConversation() {
  stopping = true;
  active = false;
  if (monitorFrame) cancelAnimationFrame(monitorFrame);
  monitorFrame = null;
  chatAbortController?.abort();
  stopSpeaking();

  if (recorder && recorder.state !== "inactive") recorder.stop();
  recorder = null;
  microphoneSource?.disconnect();
  audioContext?.close().catch(() => {});
  microphoneStream?.getTracks().forEach((track) => track.stop());
  microphoneSource = null;
  analyser = null;
  audioContext = null;
  microphoneStream = null;
  vadReady = false;
  speechCandidateFrames = 0;
  resetActiveMessages();
  elements.start.disabled = false;
  elements.stop.disabled = true;
  elements.language.disabled = false;
  elements.vadSensitivity.disabled = false;
  elements.scenario.disabled = false;
  elements.emotion.disabled = false;
  elements.voice.disabled = false;
  setStatus("Не подключён", "offline");
  setOrb("idle", "Готов к разговору");
  elements.latency.textContent = "Ожидание подключения";
}

function clearTranscript() {
  stopSpeaking();
  chatAbortController?.abort();
  elements.transcript.querySelectorAll(".message").forEach((message) => message.remove());
  elements.empty.hidden = false;
  resetScenarioState();
  resetActiveMessages();
}

function testTts() {
  stopSpeaking();
  queueSpeech("Привет! Это тест эмоциональной озвучки OpenRouter.", speechGeneration);
}

elements.start.addEventListener("click", startConversation);
elements.stop.addEventListener("click", stopConversation);
elements.ttsTest.addEventListener("click", testTts);
elements.clear.addEventListener("click", clearTranscript);
elements.vadSensitivity?.addEventListener("change", persistVadProfile);
elements.scenario?.addEventListener("change", () => {
  if (!active) resetScenarioState();
});
window.addEventListener("beforeunload", stopConversation);

restoreVadProfile();
resetScenarioState();
