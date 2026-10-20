"""Разметка текста для синтеза речи (F3): как донести до модели неречевые звуки и волнение заявителя.

Состояние приходит в `VoiceProfile` нейтрально — `sounds` и `agitation`. Модели понимают разное:
- **Gemini TTS** читает текст дословно, а звуки и паузы берёт из тегов в угловых скобках прямо в тексте: `<sob>`,
  `<gasp>`, `<short pause>`; ударение — словом заглавными («СКОРЕЕ»). Теги — по-английски и в русском тексте
  (ai.google.dev/gemini-api/docs/speech-generation, проверено 20.10.2026).
- **MAI Voice через OpenRouter и Piper** стиль не принимают: SSML MAI через OpenRouter читает вслух, а русские
  голоса MAI не знают стилей страха и крика (learn.microsoft.com/azure/ai-services/speech-service/mai-voices).
  Остаётся текст: восклицания вместо точек, повтор междометия. Замер 20.10.2026: так у MAI шире диапазон высоты
  голоса, чем от параметра скорости.

Факты реплики не меняются: только знаки препинания, регистр и повтор междометия в начале.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# звук → тег Gemini TTS; звука нет в словаре (hangup) — он не озвучивается
GEMINI_TAGS = {
    "sob": "<sob>",
    "sniff": "<whimper>",
    "scream": "<scream>",
    "gasp": "<gasp>",
    "pant": "<pant>",
    "laugh": "<laugh>",
    "sigh": "<sigh>",
    "cough": "<cough>",
    "pause": "<long pause>",
    "whisper": "<whispers>",
}
BREATH_SOUNDS = frozenset({"gasp", "pant", "sob"})
MAX_SOUNDS = 2  # больше двух звуков на реплику — заявитель звучит карикатурно
# междометия, которые взволнованный заявитель повторяет («Помогите! Помогите, у нас пожар!»)
REPEATABLE = frozenset({"алло", "помогите", "скорее", "быстрее", "пожалуйста", "господи"})
EMPHASIS = re.compile(r"\b(скорее|быстрее|помогите|срочно)\b", re.IGNORECASE)

_SENTENCES = re.compile(r"(?<=[.!?…])\s+")
# точка в конце предложения, а не в сокращении: перед ней слово из трёх и больше букв («ул.», «д.» не трогаем)
_FINAL_DOT = re.compile(r"(?<=[а-яёa-z]{3})\.(?=\s+[А-ЯЁA-Z]|\s*$)")
_FINAL_QUESTION = re.compile(r"\?(?=\s|$)")
_FIRST_WORD = re.compile(r"^\s*([А-Яа-яЁё]+)")


def _known(sounds: Sequence[str]) -> list[str]:
    seen: list[str] = []
    for s in sounds:
        if s in GEMINI_TAGS and s not in seen:
            seen.append(s)
    return seen[:MAX_SOUNDS]


def gemini_markup(text: str, sounds: Sequence[str] = (), agitation: int = 0) -> str:
    """Текст для Gemini TTS: первый звук — в начале реплики, второй — перед второй фразой (или в конце).

    При сильном волнении (3) без звука дыхания — `<heavy breath>` между фразами и ударение на «скорее/помогите»."""
    parts = _SENTENCES.split(text.strip())
    tags = [GEMINI_TAGS[s] for s in _known(sounds)]
    if tags:
        parts[0] = f"{tags[0]} {parts[0]}"
    if len(tags) > 1:
        if len(parts) > 1:
            parts[1] = f"{tags[1]} {parts[1]}"
        else:
            parts[0] = f"{parts[0]} {tags[1]}"
    elif agitation >= 3 and not BREATH_SOUNDS & set(sounds) and len(parts) > 1:
        parts[1] = f"<heavy breath> {parts[1]}"
    out = " ".join(parts)
    if agitation >= 3:
        out = EMPHASIS.sub(lambda m: m.group(0).upper(), out, count=1)
    return out


def agitate(text: str, agitation: int = 0) -> str:
    """Текст для движка без стиля (MAI через OpenRouter, Piper): волнение — пунктуацией.

    2 — точки в конце предложений становятся восклицаниями; 3 — ещё «?!» и повтор междометия в начале."""
    if agitation < 2:
        return text
    out = _FINAL_DOT.sub("!", text.strip())
    if agitation >= 3:
        out = _FINAL_QUESTION.sub("?!", out)
        m = _FIRST_WORD.match(out)
        if m and m.group(1).lower() in REPEATABLE:
            word = m.group(1)
            out = f"{word[0].upper()}{word[1:].lower()}! {out}"
    return out
