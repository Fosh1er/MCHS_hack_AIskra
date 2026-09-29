"""Офлайн-классификатор действий оператора (п. 3.6): реплика → коды `OperatorAct`.

Словари собраны из официальных источников — docs/research/psychology/05_Навыки_оператора_и_оценка.md §3:
- запреты «успокойтесь», «возьмите себя в руки», «не плачьте», обесценивание, пощёчина и вода при истерике —
  пособия ЦЭПП МЧС 2012 и 2023, пособие Минздрава «Первая помощь» 2025, МР Минпросвещения 2025;
- речевой стандарт (без частицы «не» в инструкциях, без слов «паника», «ужас», «катастрофа») — Минздрав 2025;
- повторная настойчивость (та же просьба теми же словами, с обоснованием) — IAED, APCO ANS 3.103.3-2025 п. 7.2.1;
- прямой вопрос о суициде — NENA-STA-001; «тёплая» передача — NENA-STA-020.1.

С моделью те же коды размечает ИИ-задача PSY_ACTS (закрытый список), результат объединяется с событиями по времени.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from aiskra.modules.training.domain.actors import topic_of


def norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in parts))


# ---------------------------------------------------------------- правильные действия
GREET = _rx(r"\b(служба|112|сто двенадцать|оператор|слушаю|здравствуйте|добрый (день|вечер))\b")
ASK_OPEN = _rx(r"\b(расскажите|опишите|что вы видите|что происходит|что (у вас )?случилось|что именно)\b")
ACK = _rx(
    r"\b(я )?(вас )?понимаю\b",
    r"\bслышу,? (что|как)\b",
    r"\bвам (сейчас )?(страшно|тяжело|больно|плохо|трудно)\b",
    r"\bэто (очень )?(тяжело|страшно|трудно)\b",
    r"\bпредставляю,? как\b",
    r"\bсочувствую\b",
    r"\bвижу,? (что|как) вам\b",
)
PRESENCE = _rx(
    r"\bя (на линии|с вами|здесь|рядом|никуда не ухожу|остаюсь)\b",
    r"\bне (кладите|вешайте|бросайте) трубку\b",
    r"\bоставайтесь (на линии|со мной|на связи)\b",
    r"\bя вас (слушаю|слышу)\b",
    r"\bмы (вместе|справимся)\b",
)
INFO_HELP = _rx(
    r"\b(помощь|бригада|скорая|пожарные|полиция|спасатели|наряд|врачи)\b.{0,30}"
    r"\b(направлен|выехал|едут|едет|в пути|вызван|отправлен|уже)\w*",
    r"\bя (уже )?(вызываю|передаю|направляю|отправляю|вызвал|вызвала|передал|передала)\b",
    r"\bпомощь (уже )?(идет|едет|в пути)\b",
)
BREATHING = _rx(
    r"\bдыши\w*",
    r"\bвдох\w*",
    r"\bвыдох\w*",
    r"\b(посчитайте|считайте|давайте посчитаем)\b",
    r"\bназовите,? что вы (видите|слышите)\b",
)
AFFIRM = _rx(
    r"\bвы (все|всё) (делаете )?правильно\b",
    r"\b(вы )?молодец\b",
    r"\bвы (отлично|хорошо) справляетесь\b",
    r"\bправильно,? (продолжайте|так)\b",
    r"\bхорошо,? продолжайте\b",
    r"\bвы (очень )?помогаете\b",
)
ACK_PREFIX = re.compile(r"^(понял|поняла|понятно|ясно|хорошо|слышу вас|принято|записал|записала)\b")
BOUNDARY = _rx(
    r"\bразговор записывается\b",
    r"\bвызов (записывается|фиксируется)\b",
    r"\bдавайте по делу\b",
    r"\bя (готов|готова|хочу) (вам )?помочь,? (но|для этого)\b",
    r"\bложн\w+ вызов\w*",
    r"\bответственност\w+",
)
ASK_SUICIDE = _rx(
    r"\bпокончить с собой\b",
    r"\bсуицид\w*",
    r"\b(убить|навредить|причинить вред) себ\w*",
    r"\bсвести сч[её]ты\b",
    r"\bуйти из жизни\b",
    r"\bне хотите жить\b",
    r"\bхотите умереть\b",
    r"\bмысли о смерти\b",
)
CALL_PSY = _rx(r"\bпсихолог\w*", r"\bсоединяю (вас )?со специалист\w*", r"\bподключаю (к разговору )?специалист\w*")
HANDOFF = _rx(r"\b(я )?(останусь|остаюсь) на линии\b", r"\bсейчас (подключ|соедин)\w+", r"\bне кладите трубку\b")
ASK_OTHER = _rx(
    r"\bпередайте (трубку|телефон)\b",
    r"\b(есть )?кто-(то|нибудь) рядом\b",
    r"\bдайте (трубку|телефон)\b",
    r"\bкто рядом с вами\b",
)
JUSTIFY = _rx(r"\bчтобы\b", r"\bмне нужн\w+", r"\bнужен адрес\b", r"\bбез адреса\b", r"\bдля того\b", r"\bэто важно\b")
ASK_WORDS = ("скажите", "назовите", "повторите", "подскажите", "уточните", "расскажите", "опишите", "продиктуйте")
IMPERATIVE = re.compile(
    r"(?:^|[.!?]\s*)(?:пожалуйста,?\s*|сейчас\s+|теперь\s+|срочно\s+|немедленно\s+)?(?!не\s)([а-я]+(?:ите|йте))\b"
)
NOT_INSTRUCT = ("здравствуйте", "простите", "извините", "слушайте", "понимаете", "знаете", "представьте")
NEG_IMPERATIVE = re.compile(r"(?:^|[.!?,]\s*)не\s+([а-я]+(?:ите|йте))\b")
NEG_OK = ("кладите", "вешайте", "бросайте", "отключайтесь", "прерывайте", "беспокойтесь", "волнуйтесь")

# ---------------------------------------------------------------- запрещённые действия
CALM_DOWN = _rx(
    r"\bуспокойтесь\b",
    r"\bуспокойся\b",
    r"\bне паникуй\w*",
    r"\bне плачь\w*",
    r"\bне нервничай\w*",
    r"\bне волнуйтесь\b",
    r"\bне истери\w*",
    r"\bвозьмите себя в руки\b",
    r"\bсоберитесь\b",
    r"\b(перестаньте|хватит|прекратите) (кричать|плакать|паниковать|истерить|истерику|реветь|орать)\b",
)
DEVALUE = _rx(
    r"\bерунда\b",
    r"\bничего страшного\b",
    r"\bне преувеличивайте\b",
    r"\bне выдумывайте\b",
    r"\bпросто нервы\b",
    r"\bничего особенного\b",
    r"\bне драматизируйте\b",
    r"\bбывает и хуже\b",
    r"\bпустяк\w*",
    r"\bвам (просто )?(кажется|показалось)\b",
    r"\bэто (просто )?демонстраци\w+",
)
BLAME = _rx(
    r"\bзачем вы\b",
    r"\bпочему вы (не|раньше)\b",
    r"\bсами виноваты\b",
    r"\bкак вам не стыдно\b",
    r"\bвы (должны|обязаны)\b",
    r"\bопять вы\b",
    r"\bнадо было\b",
    r"\bо ч[её]м вы думали\b",
    r"\bсоберитесь уже\b",
)
RUDE = _rx(
    r"\bчто вы орете\b",
    r"\bне орите\b",
    r"\bне кричите на меня\b",
    r"\bотстаньте\b",
    r"\bзаткн\w*",
    r"\bдура\w*",
    r"\bидиот\w*",
    r"\bбред какой\b",
    r"\bвы (что,? )?(не слышите|глухой|глухая|тупой|тупая)\b",
    r"\bсколько (можно|раз) повторять\b",
    r"\bя же (вам )?(сказал|сказала|спросил|спросила)\b",
    r"\bне тратьте мо[её] время\b",
)
THREAT_HANGUP = _rx(
    r"\b(положу|брошу) трубку\b",
    r"\bотключусь\b",
    r"\b(прекращу|закончу|прекращаю|заканчиваю) (разговор|звонок)\b",
    r"\bразговор окончен\b",
    r"\bперезвоните,? когда успокоитесь\b",
)
ARGUE = _rx(
    r"\bэто не так\b",
    r"\bвы ошибаетесь\b",
    r"\bникто за вами не\b",
    r"\bтакого не бывает\b",
    r"\bэто неправда\b",
    r"\bне может быть\b",
    r"\bвы (все|всё) неправильно\b",
)
FALSE_PROMISE = _rx(
    r"\bвс[её] будет хорошо\b",
    r"\bчерез (минуту|пару минут|две минуты|2 минуты|одну минуту) (будут|приедут)\b",
    r"\bничего (плохого )?не случится\b",
    r"\b(точно|обязательно) (выживет|спасут|успеют)\b",
    r"\bприедут через минуту\b",
)
FALSE_ADVICE = _rx(
    r"\b(плесните|облейте|брызните)\b",
    r"\bпощечин\w*",
    r"\bударьте (его|ее) по (щеке|лицу)\b",
    r"\b(потрясите|встряхните|трясите) (его|ее)\b",
)
TRIGGER_WORD = _rx(r"\bпаник\w*", r"\bкатастроф\w*", r"\bужас\w*", r"\bкошмар\w*")
JARGON = _rx(
    r"\bцов\b",
    r"\bксп\b",
    r"\bсмп\b",
    r"\bеддс\b",
    r"\bддс\b",
    r"\bрегламент\w*",
    r"\bобращение зарегистрировано\b",
    r"\bоформляю карточку\b",
    r"\bабонент\w*",
    r"\bв соответствии с\b",
)


@dataclass(frozen=True)
class ActContext:
    """Что известно классификатору о разговоре (без эталона)."""

    first_turn: bool = False
    applicant_first_name: str | None = None  # имя, если заявитель его уже назвал
    revealed: frozenset[str] = frozenset()  # темы, которые заявитель уже сообщил
    confirmed: frozenset[str] = frozenset()  # темы, которые оператор уже подтвердил
    address_tokens: tuple[str, ...] = ()  # слова адреса, если он уже прозвучал: улица, дом
    previous_operator: Sequence[str] = field(default_factory=tuple)  # прошлые реплики оператора, по порядку
    persist_run: int = 0  # сколько раз подряд уже повторена та же просьба


@dataclass(frozen=True)
class Act:
    code: str
    quote: str = ""


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[а-яa-z0-9]+", s) if len(w) > 2}


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(norm(a)), _tokens(norm(b))
    return len(ta & tb) / max(1, len(ta | tb))


def _find(rx: re.Pattern[str], t: str) -> str | None:
    m = rx.search(t)
    return m.group(0) if m else None


def classify_offline(text: str, ctx: ActContext) -> list[Act]:
    t = norm(text)
    acts: list[Act] = []

    def add(code: str, quote: str | None) -> None:
        if quote is not None and all(a.code != code for a in acts):
            acts.append(Act(code, quote))

    question = "?" in t or any(re.search(rf"\b{w}\b", t) for w in ASK_WORDS)
    topic = topic_of(t)
    if ctx.first_turn:
        add("GREET", _find(GREET, t))
    if ctx.applicant_first_name:
        stem = norm(ctx.applicant_first_name)[: max(3, len(ctx.applicant_first_name) - 1)]
        if re.search(rf"\b{re.escape(stem)}\w*", t):
            add("NAME_USE", ctx.applicant_first_name)
    if question and " или " in t:
        add("ASK_CHOICE", t[:60])
    add("ASK_OPEN", _find(ASK_OPEN, t))
    if question and topic is not None:
        add("ASK_CLOSED", t[:60])
    if ctx.address_tokens and (question or re.search(r"\b(верно|правильно|подтвердите)\b", t)):
        hits = [w for w in ctx.address_tokens if w and re.search(rf"\b{re.escape(w)}\b", t)]
        if len(hits) >= min(2, len(ctx.address_tokens)):
            add("CONFIRM", " ".join(hits))
    add("ACK_EMOTION", _find(ACK, t))
    add("PRESENCE", _find(PRESENCE, t))
    add("INFO_HELP", _find(INFO_HELP, t))
    add("BREATHING", _find(BREATHING, t))
    add("AFFIRM", _find(AFFIRM, t))
    add("BOUNDARY", _find(BOUNDARY, t))
    add("ASK_OTHER", _find(ASK_OTHER, t))
    if question:
        add("ASK_SUICIDE", _find(ASK_SUICIDE, t))
    psy = _find(CALL_PSY, t)
    add("CALL_PSY", psy)
    if psy:
        add("HANDOFF", _find(HANDOFF, t))
    for m in IMPERATIVE.finditer(t):
        verb = m.group(1)
        if verb not in ASK_WORDS and verb not in NOT_INSTRUCT:
            add("INSTRUCT", verb)
            break
    if ACK_PREFIX.search(t) and question:
        add("REDIRECT", t[:40])
    # запрещённые
    add("CALM_DOWN", _find(CALM_DOWN, t))
    add("DEVALUE", _find(DEVALUE, t))
    add("BLAME", _find(BLAME, t))
    add("RUDE", _find(RUDE, t))
    add("THREAT_HANGUP", _find(THREAT_HANGUP, t))
    add("ARGUE", _find(ARGUE, t))
    add("FALSE_PROMISE", _find(FALSE_PROMISE, t))
    add("FALSE_ADVICE", _find(FALSE_ADVICE, t))
    add("TRIGGER_WORD", _find(TRIGGER_WORD, t))
    add("JARGON", _find(JARGON, t))
    for m in NEG_IMPERATIVE.finditer(t):
        if m.group(1) not in NEG_OK:
            add("NEG_PARTICLE", m.group(0).strip(" .,!?"))
            break
    # повторы
    if topic is not None and question:
        if topic in ctx.confirmed:
            add("REASK_KNOWN", t[:60])
        elif topic not in ctx.revealed and ctx.previous_operator:
            last = ctx.previous_operator[-1]
            if topic_of(norm(last)) == topic and similarity(t, last) >= 0.5:
                if ctx.persist_run >= 3 and not JUSTIFY.search(t):
                    add("PERSIST_NO_REASON", t[:60])
                elif not _find(RUDE, t):
                    add("REPEAT_PERSIST", t[:60])
    return acts


def codes(acts: Sequence[Act]) -> set[str]:
    return {a.code for a in acts}
