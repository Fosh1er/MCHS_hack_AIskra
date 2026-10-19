# F1 — Генерация ответа в реальном времени

- **Приоритет:** P0 · **Статус:** ✅ реализовано (RF1-10 — частично)
- **Ветка:** `feat/F1-streaming` · **Решения:** [ADR-0013](../docs/adr/0013-streaming-replies.md)
- **Зависит от:** 3.6, 3.7 · **Используется в:** F3 (замеры первого токена), F4 (шкала ECCS в звонке)

## 1. Пункт плана
> [Техспека бэклога финала](../docs/brief/07_Бэклог_финала_техспека.md), раздел F1: ответ ИИ-собеседника появляется по мере генерации, озвучка — с первой фразы, метрики скорости видны.

## 2. Требования
Требования RF1-01…RF1-15 — в техспеке, раздел F1.3.

## 3. Трассировка
| ID | Реализация | Проверка | Статус | Примечание |
|---|---|---|---|---|
| RF1-01 | `ai/ports.py:LLMStreamPort`; `adapters/openai_compatible.py:stream`, `parse_sse_delta`; `adapters/fake.py:stream`; `adapters/caching.py:stream`; `ai/router.py:TaskModel.stream` | `unit/test_streaming.py` (SSE, адаптер, ошибки, кеш, без потока) | ✅ | |
| RF1-02 | `training/api/router.py:replica_stream` — события `accepted`, `state`, `model`, `token`, `remark`, `replace`, `final`, `error` | `integration/test_replica_stream.py` | ✅ | старый `POST /replicas` остался |
| RF1-03 | `calls.py:_reply` и `psy.py:PsyDirector.turn` — событие `state` до генерации | `test_psy_turn_reports_state_before_the_answer…`, `test_model_answer_streams_tokens…` | ✅ | |
| RF1-04 | `domain/stream_text.py:RemarkFilter` | `test_remark_filter_keeps_remarks_out_of_the_text` | ✅ | |
| RF1-05 | `psy.py`: `replace` при отказе `validate`; фронт показывает «заменяется», итог — из `final` | `test_psy_turn_reports_state…` | ✅ | |
| RF1-06 | `GET /calls/{id}/speak` (`application/speech.py:SpeakFragmentHandler`); `CallPanel.feedPhrases` | `test_fragment_is_spoken_in_the_callers_state`; вручную на стенде с моделью-заглушкой | ✅ | звук фраз грузится заранее |
| RF1-07 | `CallPanel.stopVoice` сбрасывает очередь фраз; перебивание — как в V3 | вручную | 🟡 | обрыв соединения генерацию не отменяет: ответ сохраняется целиком (ADR-0013) |
| RF1-08 | `CachingLLM.stream`: попадание — по словам, промах — в кеш полный ответ | `test_cache_replays_stream…` | ✅ | |
| RF1-09 | `StreamReplicaFactory` (bootstrap: своя сессия), блокировка на звонок | `integration/test_replica_stream.py` | ✅ | |
| RF1-10 | `final.metrics` (первый токен, полное время, скорость, источник, замена) | `test_model_answer_streams_tokens…` | 🟡 | в `meta.ai` реплики пока не сохраняется |
| RF1-11 | ui-kit `Transcript` (`streaming`, `fresh`, `meta`), `CallPanel.metricsLine`; «ответ по правилам» без модели | вручную | ✅ | индикатор показан всегда |
| RF1-12 | `CallPanel`: очередь голосовых реплик, отсев эха (`lastParty` копит озвученные фразы) | вручную | ✅ | |
| RF1-13 | `voice_lab.py:stream_reply`, `voice_lab_chat` — настоящий поток модели | `integration/test_voice_lab.py` | ✅ | |
| RF1-14 | заголовок `X-Accel-Buffering: no` у ответа | — | ✅ | nginx не копит поток; на стенде за cloudflared проверить |
| RF1-15 | `Actors._ask`: сбой посреди потока → `replace` и офлайн-ответ | `test_model_failure_mid_stream_is_replaced…` | ✅ | |

## 4. Решения
См. ADR-0013. Шкала состояния заявителя ECCS в панели звонка (RF4-01) сделана здесь же: её источник — событие `state`.

## 5. Критерии приёмки
- [x] Текст появляется по мере генерации, курсор и метрики видны (проверено на модели-заглушке с задержкой 0,35 с и 70 мс на слово).
- [x] Первая фраза уходит в синтез до конца ответа.
- [ ] На демо-модели p50 первого токена ≤ 1,0 с — замер на стенде с ключом (F3).

## 6. Отклонения, долги, открытые вопросы
- Метрики в БД (RF1-10) — следующий шаг, нужны для отчёта F3.
- Обрыв соединения не отменяет генерацию: это экономит целостность звонка, но тратит токены.
