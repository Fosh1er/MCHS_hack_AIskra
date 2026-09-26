"""Сборка территориальных справочников: районы Москвы и ДДС районов/поселений/префектур.

Источники (data/raw):
- moscow_districts_wikipedia_2026-09-26.json — официальный список районов (после реформы ТиНАО 2024);
- services_ocr_2026-09-17.json — справочник служб со стенда заказчика (OCR).

Номенклатура — как в АРМ заказчика (ADR-0009): 125 районов «старой» схемы (Внуково — в ЗАО)
и 21 поселение ТиНАО (НАО — 11, ТАО — 10), т.к. ДДС в системе заказчика привязаны именно к ним.
Запуск: python3 data/tools/build_territorial.py  (результат — data/dictionaries/districts.yaml и services_territorial.yaml)
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[1]
OKRUG_BY_WIKI = {
    "Центральный административный округ": "CAO", "Северный административный округ": "SAO",
    "Северо-Восточный административный округ": "SVAO", "Восточный административный округ": "VAO",
    "Юго-Восточный административный округ": "YUVAO", "Южный административный округ": "YUAO",
    "Юго-Западный административный округ": "YUZAO", "Западный административный округ": "ZAO",
    "Северо-Западный административный округ": "SZAO", "Зеленоград": "ZELAO",
}
OKRUG_SHORT = {"CAO": "ЦАО", "SAO": "САО", "SVAO": "СВАО", "VAO": "ВАО", "YUVAO": "ЮВАО", "YUAO": "ЮАО",
               "YUZAO": "ЮЗАО", "ZAO": "ЗАО", "SZAO": "СЗАО", "ZELAO": "ЗелАО", "NAO": "НАО", "TAO": "ТАО"}
# Поселения ТиНАО 2012–2024 (Википедия: «Новомосковский/Троицкий административный округ», раздел «История»).
TINAO = {
    "NAO": ["Внуковское", "Воскресенское", "Десёновское", "Кокошкино", "Марушкинское", "Московский",
            "Мосрентген", "Рязановское", "Сосенское", "Филимонковское", "Щербинка"],
    "TAO": ["Вороновское", "Киевский", "Клёновское", "Краснопахорское", "Михайлово-Ярцевское",
            "Новофёдоровское", "Первомайское", "Роговское", "Щаповское", "Троицк"],
}
TINAO_CITY = {"Щербинка", "Троицк"}  # бывшие городские округа
LEGACY_EXTRA = {"Внуково": "ZAO"}     # до 2024 район Внуково входил в ЗАО
PREF_NAMES = {"CAO": "Центрального", "SAO": "Северного", "SVAO": "Северо-Восточного", "VAO": "Восточного",
              "YUVAO": "Юго-Восточного", "YUAO": "Южного", "YUZAO": "Юго-Западного", "ZAO": "Западного",
              "SZAO": "Северо-Западного", "ZELAO": "Зеленоградского"}

TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
              ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
               "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"], strict=True))


def slug(name: str) -> str:
    s = "".join(TR.get(c, c) for c in name.lower())
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def norm(s: str) -> str:
    return re.sub(r"[^а-я0-9]", "", s.lower().replace("ё", "е"))


def main() -> None:
    wiki = json.loads((DATA / "raw/moscow_districts_wikipedia_2026-09-26.json").read_text(encoding="utf-8"))
    ocr = json.loads((DATA / "raw/services_ocr_2026-09-17.json").read_text(encoding="utf-8"))["entries"]
    ocr_dds = []
    for e in ocr:
        m = re.match(r"^(Поселение|Упр\. района)\s+(.+?)\s*\((.+)\)?$", e)
        if m:
            ocr_dds.append((m.group(1), m.group(2).strip(), e.strip()))

    districts: list[dict[str, object]] = []
    for ok in wiki["okrugs"]:
        code = OKRUG_BY_WIKI.get(ok["name"])
        if not code:
            continue  # новые районы НАО/ТАО (2024) не используются в номенклатуре заказчика
        for d in ok["districts"]:
            districts.append({"name": d["name"], "okrug": code, "kind": "district"})
    for name, code in LEGACY_EXTRA.items():
        districts.append({"name": name, "okrug": code, "kind": "district", "note": "до 2024 г. — ЗАО"})
    for code, names in TINAO.items():
        for n in names:
            districts.append({"name": n, "okrug": code,
                              "kind": "city_district" if n in TINAO_CITY else "settlement"})

    services: list[dict[str, object]] = []
    used_ocr: set[str] = set()
    for d in districts:
        name = str(d["name"])
        d["code"] = slug(name)
        plain = name.replace("ё", "е")
        if plain != name:
            d["aliases"] = [plain]
        # поиск ДДС на скриншоте заказчика: точное совпадение, затем нечёткое (Бескудниково ~ Бескудниковский)
        best, score = None, 0.0
        for prefix, short, full in ocr_dds:
            r = difflib.SequenceMatcher(None, norm(short), norm(name)).ratio()
            if r > score:
                best, score = (prefix, short, full), r
        dds_code = f"DDS_{d['code'].upper()}"
        d["dds"] = dds_code
        if best and score >= 0.8 and best[2] not in used_ocr:
            used_ocr.add(best[2])
            prefix, short, full = best
            inner = full[full.find("(") + 1 : full.rfind(")")] if "(" in full else full
            services.append({"code": dds_code, "short": f"{prefix} {short}", "full": inner, "kind": "district_dds",
                             "district": d["code"], "okrug": d["okrug"], "source": "customer_screenshot"})
        else:
            kind_word = {"settlement": "поселения", "city_district": "городского округа"}.get(str(d["kind"]), "района")
            services.append({"code": dds_code, "short": f"Поселение {plain}", "full": f"ДДС {kind_word} {plain} города Москвы",
                             "kind": "district_dds", "district": d["code"], "okrug": d["okrug"], "source": "derived"})

    for code, gen in PREF_NAMES.items():
        services.append({"code": f"PREF_{code}", "short": f"Поселение {OKRUG_SHORT[code]}",
                         "full": f"ДДС префектуры {gen} административного округа города Москвы",
                         "kind": "prefecture_dds", "okrug": code, "source": "customer_screenshot"})
    services.append({"code": "PREF_TINAO", "short": "Поселение ТиНАО",
                     "full": "ДДС префектуры Троицкого и Новомосковского округов города Москвы",
                     "kind": "prefecture_dds", "okrug": "NAO", "okrugs": ["NAO", "TAO"], "source": "customer_screenshot"})
    for code in PREF_NAMES:  # ГБУ «Автомобильные дороги» округов (на стенде — 10 округов, кроме НАО/ТАО)
        short = OKRUG_SHORT[code]
        services.append({"code": f"GBU_AD_{code}", "short": f"ГБУ АД {short}", "full": f"ГБУ Автодороги {short}",
                         "kind": "okrug_roads", "okrug": code, "source": "customer_screenshot"})

    header = "# СГЕНЕРИРОВАНО data/tools/build_territorial.py — правки вносите в генератор или исходники data/raw.\n"
    (DATA / "dictionaries/districts.yaml").write_text(
        header + yaml.safe_dump({"districts": districts}, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    (DATA / "dictionaries/services_territorial.yaml").write_text(
        header + yaml.safe_dump({"services": services}, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    matched = sum(1 for s in services if s["kind"] == "district_dds" and s["source"] == "customer_screenshot")
    print(f"районов: {len(districts)}, ДДС районов: {matched} со скриншота + "
          f"{sum(1 for s in services if s['kind'] == 'district_dds') - matched} достроено, всего служб: {len(services)}")


if __name__ == "__main__":
    main()
