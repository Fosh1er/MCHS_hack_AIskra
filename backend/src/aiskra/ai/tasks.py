"""Каталог ИИ-задач. Каждой задаче в config/ai.yaml назначается провайдер, модель и политика кеша."""

from enum import StrEnum


class AITask(StrEnum):
    PROBE = "probe"  # диагностика подключения к модели
    SCENARIO_GENERATION = "scenario_generation"  # п. 3.2 — генерация сценариев и эталонов
    APPLICANT_ACTOR = "applicant_actor"  # п. 3.3 — ИИ-заявитель (роль 112)
    BRIGADE_ACTOR = "brigade_actor"  # п. 3.3 — старший группы реагирования (роль ДДС)
    SERVICE_ACTOR = "service_actor"  # п. 3.3 — диспетчер смежной службы (роль ДДС)
    JUDGE = "judge"  # п. 3.4 — оценка свободного текста
    INSIGHTS = "insights"  # п. 4.3 — инсайты по группе
    FEEDBACK_DRAFT = "feedback_draft"  # п. 4.7 — черновик отзыва преподавателя по занятию
    PSY_ACTS = "psy_acts"  # п. 3.7 — разметка действий оператора по закрытому списку
    PSY_JUDGE = "psy_judge"  # п. 3.7 — аудиоконтроль: речь оператора и состояние заявителя
