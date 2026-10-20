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

## 3. Трассировка
| ID | Реализация | Проверка | Статус | Примечание |
|---|---|---|---|---|
| RF3-конфиг | `config/ai.openrouter.yaml`: модели, голос, резервы; любую можно заменить переменной окружения | `unit/test_speech_fallback.py::test_demo_config_builds_chosen_models_with_fallbacks` | ✅ | |
| RF3-резерв | `ai/config.py`: `tts.fallback`, `stt.fallback_model`; `adapters/speech.py`: `FallbackTTS`, `FallbackSTT`; `adapters/factory.py` | `unit/test_speech_fallback.py` | ✅ | резерв выключается пустой `TTS_FALLBACK_MODEL` / `STT_FALLBACK_MODEL` |
| RF3-замер | бенчмарк `tools/bench_models.py` и отчёт `docs/validation/models_<дата>.md` | — | ⏳ | на стенде с ключом: первый токен, первая фраза, WER |

## 4. Решения
- Резервная модель — тот же сервер и ключ OpenRouter, другое имя модели: переключение без второго аккаунта.
- Резерв TTS получает подачу только темпом (`style: none`): стиль Gemini другая модель не понимает.
- Голос Zephyr — основной и у заявительницы. Мужской голос заявителя, старший группы и диспетчер службы остаются своими (`voices`).

## 5. Критерии приёмки
- [x] Конфиг собирает выбранные модели и резервы; отказ основной модели переключает на резервную.
- [ ] На стенде: заявитель отвечает выбранной LLM, голос — Gemini; отключение основной TTS — звучит MAI Voice.
- [ ] Замер первого токена и первой фразы на стенде (порог F3.2).

## 6. Открытые вопросы
- Формат ответа MAI Voice на OpenRouter предполагается `mp3` (`TTS_FALLBACK_FORMAT`) — проверить на стенде.
