"""Адресный справочник Москвы для блока «Адрес» и окна карты (п. 1.2) из OpenStreetMap (ODbL).

Источник: выгрузка Overpass API на дату сборки — дома с addr:street + addr:housenumber, улицы (highway с name),
границы районов (admin_level=8). Сырые выгрузки (~80 МБ) в git не кладутся: data/raw/osm/ в .gitignore.

Результат (коммитится, загружается командой `aiskra.cli import-addresses`):
- data/dictionaries/addresses.csv.gz — дома: улица, номер, корпус, строение, широта, долгота, район АРМ;
- data/dictionaries/districts_geo.json — упрощённые границы районов в номенклатуре АРМ (GeoJSON) для карты
  и определения района по точке.

Номенклатура районов — как в АРМ заказчика (ADR-0009): 125 районов и 21 поселение ТиНАО. В OSM ТиНАО уже
по реформе 2024 года (районы вместо поселений), поэтому районы ТиНАО сопоставлены поселениям вручную (TINAO_MAP);
точки нового района относятся к поселению, давшему району имя (ДДС в АРМ привязаны к поселениям).

Запуск (из корня репозитория):
    cd backend && uv run --with shapely python ../data/tools/build_addresses.py [--download]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import yaml
from shapely import STRtree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, mapping
from shapely.ops import linemerge, polygonize, unary_union

DATA = Path(__file__).resolve().parents[1]
RAW = DATA / "raw" / "osm"
OUT_ADDR = DATA / "dictionaries" / "addresses.csv.gz"
OUT_GEO = DATA / "dictionaries" / "districts_geo.json"
OVERPASS = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
AREA = 'area["ISO3166-2"="RU-MOW"]->.m;'
QUERIES = {
    "districts.json": f'[out:json][timeout:300];{AREA}rel(area.m)["admin_level"="8"]["boundary"="administrative"];out geom;',
    "addr.json": f'[out:json][timeout:500][maxsize:1073741824];{AREA}nwr(area.m)["addr:street"]["addr:housenumber"];out center tags qt;',
    "streets.json": f'[out:json][timeout:300];{AREA}way(area.m)["highway"]["name"];out center tags qt;',
}
SIMPLIFY_DEG = 0.00025  # ≈ 15–25 м: граница района на карте и для определения района по точке

# Районы ТиНАО после реформы 2024 (OSM) → поселение АРМ (код из districts.yaml).
TINAO_MAP = {
    "внуково": "vnukovskoe", "вороново": "voronovskoe", "десеновский": "desenovskoe", "кокошкинский": "kokoshkino",
    "краснопахорский": "krasnopakhorskoe", "марушкинский": "marushkinskoe", "московский": "moskovskiy",
    "рязановский": "ryazanovskoe", "сосенский": "sosenskoe", "филимонковский": "filimonkovskoe",
    "щербинка": "shcherbinka", "бекасово": "kievskiy", "киевский": "kievskiy", "кленовский": "klenovskoe",
    "михайловоярцевский": "mikhaylovo_yartsevskoe", "новофедоровский": "novofedorovskoe",
    "первомайский": "pervomayskoe", "роговский": "rogovskoe", "щаповский": "shchapovskoe", "троицк": "troitsk",
    "коммунарка": "sosenskoe", "воскресенский": "voskresenskoe", "мосрентген": "mosrentgen",
    "кленово": "klenovskoe", "вороновский": "voronovskoe", "внуковский": "vnukovskoe",
    "новомосковский": "moskovskiy", "рогово": "rogovskoe", "щапово": "shchapovskoe",
}


def norm(s: str) -> str:
    return re.sub(r"[^а-я0-9]", "", s.lower().replace("ё", "е"))


def district_key(name: str) -> str:
    """«район Арбат», «Басманный район», «поселение Вороновское» → «арбат», «басманный», «вороновское»."""
    s = re.sub(r"\b(район|поселение|муниципальный округ|городской округ|город)\b", " ", name.lower().replace("ё", "е"))
    return norm(s)


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, query in QUERIES.items():
        for attempt in range(6):
            req = urllib.request.Request(
                OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(), headers={"User-Agent": "AIskra/1.0"}
            )
            try:
                body = urllib.request.urlopen(req, timeout=900).read()
            except OSError as e:
                print(f"{name}: попытка {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(20)
                continue
            if body.lstrip().startswith(b"{"):
                (RAW / name).write_bytes(body)
                print(f"{name}: {len(body) // 1_000_000} МБ")
                break
            print(f"{name}: попытка {attempt + 1}: сервер занят", file=sys.stderr)
            time.sleep(20)
        else:
            sys.exit(f"Не удалось скачать {name}")


def relation_polygon(rel: dict) -> MultiPolygon | Polygon | None:
    """Кольца границы из геометрии членов-линий (outer минус inner)."""
    outer, inner = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        line = LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        (inner if m.get("role") == "inner" else outer).append(line)
    if not outer:
        return None
    shell = unary_union(list(polygonize(linemerge(outer))))
    if inner:
        shell = shell.difference(unary_union(list(polygonize(linemerge(inner)))))
    return shell if not shell.is_empty else None


HOUSE_RE = re.compile(
    r"^\s*(?P<house>[0-9]+[а-яa-z]?(?:/[0-9]+[а-я]?)?)"
    r"(?:\s*(?:к|корп\.?|корпус)\s*(?P<building>[0-9]+[а-я]?))?"
    r"(?:\s*(?:с|стр\.?|строение)\s*(?P<structure>[0-9]+[а-я]?))?\s*$",
    re.IGNORECASE,
)


def parse_house(raw: str) -> tuple[str, str, str] | None:
    """«6 к1 с2» → («6», «1», «2»); «16А» → («16А», «», «»). Нераспознанные номера пропускаются."""
    m = HOUSE_RE.match(raw.replace(" ", " "))
    if not m:
        return None
    house = m["house"].upper() if re.search(r"[а-яa-z]$", m["house"], re.I) else m["house"]
    return house, (m["building"] or "").upper(), (m["structure"] or "").upper()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="скачать свежую выгрузку Overpass в data/raw/osm/")
    args = ap.parse_args()
    if args.download or not all((RAW / n).exists() for n in QUERIES):
        download()

    ours = yaml.safe_load((DATA / "dictionaries/districts.yaml").read_text(encoding="utf-8"))["districts"]
    by_key: dict[str, dict] = {}
    for d in ours:
        for n in [d["name"], *d.get("aliases", [])]:
            by_key[district_key(n)] = d
    by_code = {d["code"]: d for d in ours}

    # --- границы районов
    rels = json.loads((RAW / "districts.json").read_text(encoding="utf-8"))["elements"]
    shapes: dict[str, list] = {}
    unmatched = []
    for rel in rels:
        if rel["tags"].get("admin_level") != "8":
            continue
        name = rel["tags"].get("name", "")
        key = district_key(name)
        d = by_key.get(key) or by_code.get(TINAO_MAP.get(key, ""))
        poly = relation_polygon(rel)
        if d is None or poly is None:
            unmatched.append(name)
            continue
        shapes.setdefault(d["code"], []).append(poly)
    merged = {code: unary_union(polys).simplify(SIMPLIFY_DEG, preserve_topology=True) for code, polys in shapes.items()}
    missing = sorted(d["name"] for d in ours if d["code"] not in merged)
    print(f"Районов АРМ с границей: {len(merged)} из {len(ours)}")
    if unmatched:
        print(f"Не сопоставлены районы OSM: {unmatched}", file=sys.stderr)
    if missing:
        print(f"Без границы (поселения, вошедшие в другие районы после 2024): {missing}", file=sys.stderr)

    features = []
    for code, geom in sorted(merged.items()):
        d = by_code[code]
        rp = geom.representative_point()
        features.append({
            "type": "Feature",
            "properties": {"code": code, "name": d["name"], "okrug": d["okrug"], "label": [round(rp.x, 5), round(rp.y, 5)]},
            "geometry": json.loads(json.dumps(mapping(geom), separators=(",", ":")), parse_float=lambda x: round(float(x), 5)),
        })
    OUT_GEO.write_text(
        json.dumps({"type": "FeatureCollection", "source": "OpenStreetMap (ODbL)", "features": features},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    # --- дома
    codes = list(merged)
    tree = STRtree([merged[c] for c in codes])
    def locate(lon: float, lat: float) -> str:
        pt = Point(lon, lat)
        for i in tree.query(pt, predicate="within"):
            return codes[int(i)]
        return ""

    elems = json.loads((RAW / "addr.json").read_text(encoding="utf-8"))["elements"]
    seen: set[tuple[str, str, str, str, str]] = set()
    rows = []
    skipped = Counter()
    for e in elems:
        t = e.get("tags", {})
        c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        street = " ".join(t.get("addr:street", "").split())
        parsed = parse_house(t.get("addr:housenumber", ""))
        if not c or not street:
            skipped["без координат или улицы"] += 1
            continue
        if not parsed:
            skipped["нераспознанный номер"] += 1
            continue
        house, building, structure = parsed
        district = locate(c["lon"], c["lat"])
        if not district:
            skipped["вне районов Москвы"] += 1
            continue
        key = (norm(street), house.lower(), building, structure, district)  # одноимённые улицы в разных районах
        if key in seen:
            skipped["дубль"] += 1
            continue
        seen.add(key)
        rows.append((street, house, building, structure, round(c["lat"], 6), round(c["lon"], 6), district))
    rows.sort(key=lambda r: (r[0], [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", r[1])], r[2], r[3]))

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["street", "house", "building", "structure", "lat", "lon", "district"])
    w.writerows(rows)
    with gzip.open(OUT_ADDR, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write(buf.getvalue())

    streets = {r[0] for r in rows}
    print(f"Домов: {len(rows)}, улиц: {len(streets)}; пропущено: {dict(skipped)}")
    print(f"→ {OUT_ADDR.relative_to(DATA.parent)} ({OUT_ADDR.stat().st_size // 1024} КБ), "
          f"{OUT_GEO.relative_to(DATA.parent)} ({OUT_GEO.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
