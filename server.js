import "dotenv/config";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const port = Number(process.env.PORT || 3000);

const openRouterApiKey = process.env.OPENROUTER_API_KEY;
const chatModel = process.env.OPENROUTER_MODEL || "google/gemini-3.1-flash-lite";
const chatReasoningEffort = process.env.OPENROUTER_REASONING_EFFORT || "none";
const chatMaxTokens = Number(process.env.OPENROUTER_MAX_TOKENS || 120);
const sttModel = process.env.OPENROUTER_STT_MODEL || "openai/whisper-1";
const ttsModel = process.env.OPENROUTER_TTS_MODEL || "google/gemini-3.8-flash-lite-tts";
const ttsVoice = process.env.OPENROUTER_TTS_VOICE || "Zephyr";
const siteUrl = process.env.OPENROUTER_SITE_URL || `http://localhost:${port}`;
const appName = process.env.OPENROUTER_APP_NAME || "Full Duplex Voice Agent";

const supportedVoices = new Set(["default", "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Aoede", "Orus"]);
const supportedAudioFormats = new Set(["webm", "wav", "mp3", "mp4", "m4a", "ogg", "flac"]);

app.use(express.json({ limit: "32mb" }));
app.use(express.static(path.join(__dirname, "public")));

function openRouterHeaders(contentType = "application/json") {
  return {
    Authorization: `Bearer ${openRouterApiKey}`,
    "Content-Type": contentType,
    "HTTP-Referer": siteUrl,
    "X-OpenRouter-Title": appName,
  };
}

function requireApiKey(res) {
  if (openRouterApiKey) return true;
  res.status(500).json({
    error: "OPENROUTER_API_KEY is not configured. Copy .env.example to .env and add your key.",
  });
  return false;
}

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    provider: "openrouter",
    configured: Boolean(openRouterApiKey),
    chatModel,
    chatReasoningEffort,
    chatMaxTokens,
    sttModel,
    ttsModel,
    ttsVoice,
  });
});

app.post("/api/stt", async (req, res) => {
  if (!requireApiKey(res)) return;

  const { audio, format = "webm", language = "auto" } = req.body ?? {};

  if (typeof audio !== "string" || !audio) {
    return res.status(400).json({ error: "Base64 encoded audio is required." });
  }

  if (!supportedAudioFormats.has(format)) {
    return res.status(400).json({ error: `Unsupported audio format: ${format}` });
  }

  try {
    const upstream = await fetch("https://openrouter.ai/api/v1/audio/transcriptions", {
      method: "POST",
      headers: openRouterHeaders(),
      body: JSON.stringify({
        model: sttModel,
        input_audio: { data: audio, format },
        ...(language !== "auto" ? { language } : {}),
      }),
    });

    const payload = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      console.error("OpenRouter STT error:", upstream.status, payload);
      return res.status(upstream.status).json({
        error: "OpenRouter transcription failed.",
        details: payload,
      });
    }

    return res.json({ text: payload.text || "", usage: payload.usage || null });
  } catch (error) {
    console.error("STT proxy error:", error);
    return res.status(502).json({ error: "Could not reach OpenRouter STT." });
  }
});

app.post("/api/chat", async (req, res) => {
  if (!requireApiKey(res)) return;

  const { messages, model = chatModel } = req.body ?? {};
  if (!Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ error: "A non-empty messages array is required." });
  }

  const safeMessages = messages
    .filter((message) => message && ["system", "user", "assistant"].includes(message.role))
    .map((message) => ({
      role: message.role,
      content: String(message.content || "").slice(0, 12000),
    }))
    .slice(-40);

  const systemMessage = safeMessages.find((message) => message.role === "system");
  const recentMessages = safeMessages.filter((message) => message.role !== "system").slice(-10);
  const boundedMessages = systemMessage ? [systemMessage, ...recentMessages] : recentMessages;

  try {
    const upstream = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: openRouterHeaders(),
      body: JSON.stringify({
        model,
        messages: boundedMessages,
        stream: true,
        temperature: 0.55,
        max_tokens: chatMaxTokens,
        reasoning_effort: chatReasoningEffort,
      }),
    });

    if (!upstream.ok) {
      const details = await upstream.text();
      console.error("OpenRouter chat error:", upstream.status, details);
      return res.status(upstream.status).json({
        error: "OpenRouter chat completion failed.",
        details,
      });
    }

    res.status(200);
    res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache, no-transform");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");

    for await (const chunk of upstream.body) {
      res.write(chunk);
    }
    res.end();
  } catch (error) {
    console.error("Chat proxy error:", error);
    if (!res.headersSent) res.status(502).json({ error: "Could not reach OpenRouter chat." });
    else res.end();
  }
});

app.post("/api/tts", async (req, res) => {
  if (!requireApiKey(res)) return;

  const { input, voice = ttsVoice, model = ttsModel } = req.body ?? {};
  if (typeof input !== "string" || !input.trim()) {
    return res.status(400).json({ error: "Text input is required." });
  }
  if (input.length > 4000) {
    return res.status(400).json({ error: "TTS input is limited to 4000 characters per segment." });
  }
  if (!model.startsWith("fish-audio/") && !supportedVoices.has(voice)) {
    return res.status(400).json({ error: `Unsupported voice: ${voice}` });
  }

  try {
    const upstream = await fetch("https://openrouter.ai/api/v1/audio/speech", {
      method: "POST",
      headers: openRouterHeaders(),
      body: JSON.stringify({
        model,
        input,
        ...(model.startsWith("fish-audio/") ? {} : { voice }),
        response_format: model.startsWith("google/gemini-") ? "pcm" : "mp3",
        speed: 1.04,
      }),
    });

    if (!upstream.ok) {
      const details = await upstream.text();
      console.error("OpenRouter TTS error:", upstream.status, details);
      return res.status(upstream.status).json({
        error: "OpenRouter speech synthesis failed.",
        details,
      });
    }

    const audio = Buffer.from(await upstream.arrayBuffer());
    const isPcm = model.startsWith("google/gemini-");
    const output = isPcm ? pcmToWav(audio) : audio;
    res.setHeader("Content-Type", isPcm ? "audio/wav" : upstream.headers.get("content-type") || "audio/mpeg");
    res.setHeader("Cache-Control", "no-store");
    const generationId = upstream.headers.get("x-generation-id");
    if (generationId) res.setHeader("X-Generation-Id", generationId);
    res.send(output);
  } catch (error) {
    console.error("TTS proxy error:", error);
    res.status(502).json({ error: "Could not reach OpenRouter TTS." });
  }
});

function pcmToWav(pcm, sampleRate = 24000, channels = 1, bitsPerSample = 16) {
  const header = Buffer.alloc(44);
  const byteRate = sampleRate * channels * bitsPerSample / 8;
  const blockAlign = channels * bitsPerSample / 8;

  header.write("RIFF", 0, "ascii");
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write("WAVE", 8, "ascii");
  header.write("fmt ", 12, "ascii");
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36, "ascii");
  header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}

app.get("/{*splat}", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(port, () => {
  console.log(`OpenRouter voice agent is running at http://localhost:${port}`);
});
