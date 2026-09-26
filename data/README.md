# Данные

| Папка | Что | Правило |
|---|---|---|
| `source/` | Оригиналы заказчика: `classifier_v046.xlsx` — классификатор происшествий v046 (чат задачи #483) | Не редактировать. Новая версия — новый файл + обновить путь в `Settings.classifier_path` |
| `raw/` | Сырые выгрузки с указанием источника и даты: OCR справочника служб (`СЛУЖБЫ 112.docx`), районы Москвы (Википедия), список типов «Что случилось». `raw/osm/` — выгрузка OpenStreetMap (~80 МБ, в git не кладётся) | Только добавлять. Используются генераторами |
| `dictionaries/` | Выверенные справочники YAML — то, что загружает импорт | Правки через PR. Файлы с шапкой «СГЕНЕРИРОВАНО» меняются только генератором |
| `tools/` | Генераторы: `build_territorial.py` → `districts.yaml`, `services_territorial.yaml`; `build_addresses.py` → `addresses.csv.gz`, `districts_geo.json` | `python3 data/tools/build_territorial.py`; `cd backend && uv run --with shapely python ../data/tools/build_addresses.py [--download]` |

## Справочники (`dictionaries/`)
| Файл | Содержимое |
|---|---|
| `classifier_columns.yaml` | Разметка 76 колонок матрицы служб: служба, признак, базовая / постоянная, аудитория |
| `services_core.yaml` | 54 городские, федеральные и экстренные службы (`confirmed: false` — расшифровка наша) |
| `services_territorial.yaml` | ДДС районов и поселений (146), префектур (11), ГБУ АД округов (10) — генерируется |
| `districts.yaml` | 146 районов и поселений в номенклатуре АРМ заказчика — генерируется |
| `okrugs.yaml` | 12 округов + «МО» |
| `card_types.yaml` | 51 тип «Что случилось?» → группа классификатора, синонимы, частые / значимые |
| `enums.yaml` | Статусы заявителя, карточки, службы, телефонии; признаки карточки |
| `channels.yaml` | Каналы связи |
| `addresses.csv.gz` | Адресный справочник (п. 1.2): 128 677 домов, 4 625 улиц — улица, дом, корпус, строение, координаты, район АРМ. OpenStreetMap (ODbL) — генерируется |
| `districts_geo.json` | Упрощённые границы 132 районов в номенклатуре АРМ (GeoJSON) для карты и района по точке — генерируется |

**Загрузка в БД:** `cd backend && uv run python -m aiskra.cli import-dictionaries`, затем `uv run python -m aiskra.cli import-addresses` (адреса и границы, п. 1.2). Описание модели — [specs/0.2-data-model.md](../specs/0.2-data-model.md).
