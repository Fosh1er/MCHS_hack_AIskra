# F3 — Модели ИИ для быстрых ответов

- **Приоритет:** P1 · **Статус:** 🟡 модели выбраны командой и подключены; замер на стенде — впереди
- **Ветка:** `feat/F3-models` · **Решения:** ADR-0003 (порты ИИ), ADR-0011 (голос)

## 1. Пункт плана
> [Техспека бэклога финала](../docs/brief/07_Бэклог_финала_техспека.md), раздел F3: модели LLM, TTS и STT под быстрые ответы, выбор по замерам.

## 2. Выбор команды (19.10.2026)
| Задача | Основная | Резерв |
|---|---|---|
| LLM — реплики собеседников, разметка реплик (`demo_small`) | `qwen/qwen3.8-flash` | переменная `DEMO_SMALL_MODEL` |
| LLM — генерация сценариев, ИИ-судья, отзыв (`demo`) | `openai/gpt-4o` | переменная `DEMO_LLM_MODEL` |
| TTS (голос собеседника) | `google/gemini-3.8-flash-tts`, голос Zephyr | `microsoft/mai-voice-2.1-flash`, голос `ru-RU-Masha:MAI-Voice-2.1-Flash` |
| STT (речь оператора) | `qwen/qwen3-asr-0.6b` | `openai/whisper-large-v3-turbo` |

Проверка по каталогу OpenRouter (`/api/v1/models`, 20.10.2026):
- все пять моделей есть;
- у Gemini TTS есть голоса Zephyr, Charon, Orus, Aoede;
- у MAI Voice — `ru-RU-Masha` (ещё `ru-RU-Lev`, `ru-RU-Grant`, `ru-RU-Harper`);
- `qwen/qwen3.8-flash` поддерживает `response_format`, `structured_outputs`, `reasoning`; цена 0,15 / 0,47 $ за 1 млн токенов против 2,5 / 10 $ у gpt-4o;
- у Gemini TTS два поставщика (AI Studio и Vertex) — стиль голоса передаётся обоим.

Как заставить модели звучать эмоционально (документация, 20.10.2026):
- **Gemini 3.8 Flash TTS** ([speech-generation](https://ai.google.dev/gemini-api/docs/speech-generation)):
  - подача — в `speech_metadata.style`, короткой строкой («whispered urgently»); длинные «режиссёрские заметки» уводят голос, постоянные черты (возраст) — не в стиль, а в Voice design;
  - звуки и паузы — тегами в угловых скобках в тексте, по-английски и в русском тексте: `<sob>`, `<gasp>`, `<pant>`, `<sigh>`, `<cough>`, `<scream>`, `<whimper>`, `<short pause>`, `<long pause>`; квадратные скобки не документированы;
  - ударение — словом заглавными, запинки — многоточием и тире;
  - русский поддерживается.
- **MAI-Voice-2.1-Flash** ([mai-voices](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-voices)):
  - эмоция — только SSML `<mstts:express-as style="…">`;
  - у русских голосов (`ru-RU-Masha`, `ru-RU-Lev`) нет стилей страха, гнева, крика и шёпота — только `excited`, `saddisappointed`, `serious`, `caringempathy` и спокойные;
  - через OpenRouter SSML не разбирается — теги читаются вслух (замер 20.10.2026: 30 с вместо 9), стиль в `provider.options` — ответ 400, `speed` почти не влияет;
  - остаётся текст: восклицания и повтор междометия — по замеру шире диапазон высоты голоса.

## 3. Трассировка
| ID | Реализация | Проверка | Статус | Примечание |
|---|---|---|---|---|
| RF3-конфиг | `config/ai.openrouter.yaml`: модели, голос, резервы; любую можно заменить переменной окружения | `unit/test_speech_fallback.py::test_demo_config_builds_chosen_models_with_fallbacks` | ✅ | |
| RF3-резерв | `ai/config.py`: `tts.fallback`, `stt.fallback_model`; `adapters/speech.py`: `FallbackTTS`, `FallbackSTT`; `adapters/factory.py` | `unit/test_speech_fallback.py` | ✅ | резерв выключается пустой `TTS_FALLBACK_MODEL` / `STT_FALLBACK_MODEL` |
| RF3-эмоции | подача по документации моделей: `VoiceProfile.sounds`/`agitation` (`ai/ports.py`), домен — `training/domain/voice_cues.py` (уровень ECCS или напряжение → волнение 0–3; ремарки, звуки профиля, дыхание, кашель при дыме → звуки); разметка — `ai/adapters/speech_markup.py` (`gemini_markup` — теги, `agitate` — пунктуация), выбор по `style` — `OpenAICompatibleTTS._markup`; короткий `speech_style`; фраза потока — `GET /calls/{id}/speak?tension=&level=&remarks=`, фронт — `CallPanel` (`PhraseCue`) | `unit/test_speech_markup.py`, `unit/test_voice_cues.py`, `unit/test_speech.py::test_tts_sounds_and_agitation_by_style`, `integration/test_replica_stream.py::test_fragment_is_spoken_in_the_callers_state`, `integration/test_speech_audio.py::test_replica_audio` | ✅ | MAI вживую — 20.10.2026; Gemini вживую — после пополнения баланса OpenRouter |
| RF3-замер | бенчмарк `tools/bench_models.py` и отчёт `docs/validation/models_<дата>.md` | — | ⏳ | на стенде с ключом: первый токен, первая фраза, WER |

## 4. Решения
- Резервная модель — тот же сервер и ключ OpenRouter, другое имя модели: переключение без второго аккаунта.
- Резерв TTS получает подачу темпом и пунктуацией (`style: none`): стиль Gemini другая модель не понимает, а SSML MAI через OpenRouter не проходит.
- Звуки и волнение — нейтрально в `VoiceProfile`, разметка под модель — в адаптере: смена модели не трогает домен. Текст реплики в звонке не меняется — факты легенды остаются дословными.
- Голос Zephyr — основной и у заявительницы. Мужской голос заявителя, старший группы и диспетчер службы остаются своими (`voices`).

## 5. Критерии приёмки
- [x] Конфиг собирает выбранные модели и резервы; отказ основной модели переключает на резервную.
- [ ] На стенде: заявитель отвечает выбранной LLM, голос — Gemini; отключение основной TTS — звучит MAI Voice.
- [ ] Замер первого токена и первой фразы на стенде (порог F3.2).

## 6. Открытые вопросы
- Формат ответа MAI Voice на OpenRouter предполагается `mp3` (`TTS_FALLBACK_FORMAT`) — проверить на стенде.
