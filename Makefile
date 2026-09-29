# Частые команды. Бэкенд: uv (Python 3.12), фронтенд: npm workspaces (Node 22).
.PHONY: up down logs be-install be-test be-lint be-check fe-install fe-dev fe-dev-lan dev-cert dev-tts dev-tts-say dev-stt fe-build check import-classifier demo-seed demo-seed-docker

up:            ; docker compose up --build -d
down:          ; docker compose down
logs:          ; docker compose logs -f backend
be-install:    ; cd backend && uv sync
be-test:       ; cd backend && uv run pytest -q
be-lint:       ; cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
be-check: be-lint be-test
# M6: стенд одной командой (справочники, адреса, сценарии, учётки ролей, группа). Пароль — AISKRA_DEMO_PASSWORD.
demo-seed:     ; cd backend && uv run python -m aiskra.cli demo-seed $(if $(MATERIALS),--materials $(MATERIALS),)
demo-seed-docker: ; docker compose exec -e AISKRA_DEMO_PASSWORD backend python -m aiskra.cli demo-seed
demo-history:  ; cd backend && uv run python tools/demo_history.py
demo-history-docker: ; docker compose exec -e AISKRA_DEMO_PASSWORD backend python tools/demo_history.py
fe-install:    ; npm install
fe-dev:        ; npm run dev
# HTTPS для коллег в локальной сети: сертификат на IP этой машины (голосовой ввод требует https)
dev-cert:
	@mkdir -p .cert && IP=$$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d' ' -f1) && \
	openssl req -x509 -newkey rsa:2048 -nodes -days 30 -keyout .cert/dev.key -out .cert/dev.crt -subj "/CN=АИскра dev" \
	  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1$${IP:+,IP:$$IP}" 2>/dev/null && \
	echo "Сертификат для localhost и $$IP — .cert/dev.crt (30 дней). Клиент: make fe-dev-lan → https://$$IP:5173"
fe-dev-lan:    ; npm run dev -w frontend -- --host
# п. 3.6: голос собеседника без ключей и Docker — нейроголоса Piper (irina, denis, dmitri; скачаются при первом запуске);
# сервер: TTS_KIND=openai_compatible TTS_URL=http://localhost:8100/v1 TTS_FORMAT=wav + голоса ролей — docs/ai/Голосовой_ввод.md
dev-tts:       ; cd backend && uv run --with sherpa-onnx --with numpy python tools/dev_tts_piper.py
# то же на голосе macOS (say, Milena) — ничего не скачивает, один голос на все роли
dev-tts-say:   ; cd backend && uv run python tools/dev_tts_say.py
# распознавание речи на процессоре без Docker и ключей — faster-whisper (модель small скачается при первом запуске); сервер: STT_KIND=openai_compatible STT_URL=http://localhost:8200/v1
dev-stt:       ; cd backend && uv run --with faster-whisper python tools/dev_stt_whisper.py
fe-build:      ; npm run typecheck && npm run build
check: be-check fe-build
