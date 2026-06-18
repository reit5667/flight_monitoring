# Dev Notes — объяснения по ходу разработки

Этот файл — объяснения нетривиальных решений: почему так, а не иначе.
Читай после каждой сессии чтобы понять что было сделано и почему.

## Содержание

- [Как работают тесты](#как-работают-тесты-в-этом-проекте)
- [TASK-004 — SQL миграции: warehouse таблицы](#task-004--sql-миграции-warehouse-таблицы)
- [TASK-005 — Seed MVP маршрутов](#task-005--seed-mvp-маршрутов)
- [TASK-008 — Pydantic модели: Flight, Route, SourceMapping](#task-008--pydantic-модели-flight-route-sourcemapping)
- [TASK-009 — Pydantic модели: CdcEvent, RawSnapshot](#task-009--pydantic-модели-cdcevent-rawsnapshot)
- [TASK-010 — Абстрактный базовый класс Connector](#task-010--абстрактный-базовый-класс-connector)
- [TASK-011 — Raw Storage: save_raw и load_raw](#task-011--raw-storage-save_raw-и-load_raw)
- [TASK-012 + TASK-013 — Aviasales: от Playwright к Travelpayouts API](#task-012--task-013--aviasales-от-playwright-к-travelpayouts-api)
- [TASK-016 — Search Planner: оркестрация коннекторов](#task-016--search-planner-оркестрация-коннекторов)
- [TASK-007 — Grafana и Prometheus в Docker Compose](#task-007--grafana-и-prometheus-в-docker-compose)
- [TASK-026 — Grafana PostgreSQL datasource через provisioning](#task-026--grafana-postgresql-datasource-через-provisioning)
- [TASK-027 — Grafana дашборд: история цен](#task-027--grafana-дашборд-история-цен)
- [TASK-028 + TASK-029 — Grafana Overview и Prometheus метрики](#task-028--task-029--grafana-overview-и-prometheus-метрики)
- [Travelpayouts API: формат даты в запросе](#travelpayouts-api-формат-даты-в-запросе)
- [Grafana: source vs provider в flights_history](#grafana-source-vs-provider-в-flights_history)
- [Безопасность: .env vs .env.example](#безопасность-env-vs-envexample)
- [Как запустить и потрогать проект руками](#как-запустить-и-потрогать-проект-руками)

---

## Как работают тесты в этом проекте

### Что такое тест

Тест — это функция которая вызывает твой код и проверяет что результат совпадает с ожидаемым. Если не совпадает — тест "падает" (FAILED) и показывает где именно расхождение.

```python
def test_save_raw_returns_snapshot_with_id():
    snapshot = save_raw({"test": 1}, "aviasales", 1)  # вызываем наш код
    assert snapshot.id is not None and snapshot.id > 0  # проверяем результат
```

`assert` — ключевое слово Python. Если выражение справа истинно — тест продолжается. Если ложно — pytest остановит выполнение и покажет ошибку с подробностями.

### Как запускать

```bash
# все тесты
.venv/bin/python -m pytest

# тесты конкретного файла
.venv/bin/python -m pytest tests/test_storage_raw.py

# с подробным выводом (имена каждого теста)
.venv/bin/python -m pytest -v
```

Вывод `7 passed` — все 7 тестов прошли. `FAILED` — хотя бы один упал.

### Два типа тестов в проекте

**Unit тесты** (`test_models.py`) — тестируют изолированную логику без внешних зависимостей. Pydantic-валидация не нужна БД, поэтому они запускаются мгновенно и всегда.

**Integration тесты** (`test_storage_raw.py`, `test_connector_base.py`) — тестируют реальное взаимодействие с PostgreSQL. Требуют запущенного Docker:
```bash
docker compose up -d    # поднять контейнеры перед запуском
```

### Почему тесты важны

Когда мы меняем один модуль — тесты показывают, не сломали ли мы другой. Например, после добавления поля `id` в `RawSnapshot` мы сразу видели: старые тесты (`test_models.py`) по-прежнему зелёные — поле опциональное, ничего не сломалось.

### Фикстура `monkeypatch` в тестах storage

В `test_storage_raw.py` используется `monkeypatch.setattr(raw_module, "RAW_STORAGE_DIR", tmp_path)` — это временная подмена пути к директории. Файлы пишутся во временную папку pytest, а не в `raw_storage/` репозитория. После теста pytest сам удаляет временные файлы. Сама БД при этом используется настоящая — поэтому тесты действительно проверяют работу с ней.

---

## TASK-004 — SQL миграции: warehouse таблицы

**Файл:** `migrations/002_warehouse.sql`

### Четыре таблицы и их назначение

| Таблица | Роль |
|---|---|
| `flights_current` | Витрина актуальных цен. Один рейс = одна строка. При изменении цены — UPDATE. |
| `flights_history` | Полная история. Строки только добавляются, никогда не удаляются. |
| `cdc_events` | Журнал изменений: что именно изменилось, когда, на сколько. |
| `raw_snapshots` | Метаданные о скачанных файлах: путь, источник, количество записей. |

### BIGSERIAL vs SERIAL

`SERIAL` — 4 байта, максимум ~2 миллиарда значений.
`BIGSERIAL` — 8 байт, максимум ~9 квинтиллионов.

Для `routes` хватит SERIAL — маршрутов у нас десятки. Но `flights_current`, `flights_history` и `cdc_events` будут расти постоянно: каждые N минут по каждому маршруту добавляем события. Через год на проде SERIAL может переполниться. Поэтому там `BIGSERIAL`.

### ON DELETE RESTRICT vs ON DELETE CASCADE

В первой миграции (`source_route_mappings`) стоит `CASCADE`: удалил маршрут — маппинги удалились автоматически. Это логично — маппинг без маршрута бессмысленен.

В warehouse таблицах стоит `RESTRICT`: нельзя удалить маршрут, пока есть связанные рейсы или события. PostgreSQL выбросит ошибку.

Почему? Потому что исторические данные ценны. Случайное `DELETE FROM routes WHERE ...` не должно уничтожать месяцы истории цен. `RESTRICT` — это защитный барьер: хочешь удалить маршрут — сначала сам разберись с историей.

### UNIQUE NULLS NOT DISTINCT

Появилось в PostgreSQL 15. Решает неочевидную проблему с NULL в уникальных ключах.

В SQL `NULL != NULL` — два значения NULL считаются разными (потому что NULL означает "неизвестно", и два "неизвестно" необязательно равны). Это ломает уникальный ключ: два рейса с `flight_number = NULL` не считались бы дублями, и в таблицу можно было бы вставить одни и те же чартерные рейсы сколько угодно раз.

`UNIQUE NULLS NOT DISTINCT` говорит PostgreSQL: "для целей уникальности считай NULL = NULL". Теперь два рейса с одинаковым `(provider, NULL, departure_time, route_id)` — дубли.

### TIMESTAMPTZ vs TIMESTAMP

`TIMESTAMP` — хранит дату и время без информации о таймзоне. Если сервер в UTC, а источник данных в UTC+7 — получишь путаницу.

`TIMESTAMPTZ` (timestamp with time zone) — всегда хранит в UTC, автоматически конвертирует при записи и чтении. Можно передать время в любой таймзоне — PostgreSQL сам переведёт в UTC.

Правило: **всегда используй TIMESTAMPTZ** в production системах, особенно если данные приходят из разных источников.

### Индекс WHERE is_current = true (partial index)

```sql
CREATE INDEX IF NOT EXISTS idx_flights_history_current
    ON flights_history (provider, flight_number, departure_time, route_id)
    WHERE is_current = true;
```

Обычный индекс покрывает все строки таблицы. `WHERE is_current = true` создаёт **partial index** — индекс только по актуальным записям.

Зачем? В `flights_history` будут миллионы строк исторических записей (`is_current = false`). Но запрашивать мы будем почти всегда только актуальные. Partial index в разы меньше по размеру и быстрее — он содержит только ту часть данных, которую реально ищем.

---

## TASK-005 — Seed MVP маршрутов

**Файл:** `migrations/003_seed_routes.sql`

### Почему ON CONFLICT DO NOTHING не сработал для routes

Первая версия seed использовала `ON CONFLICT DO NOTHING` для таблицы `routes`. Казалось бы — стандартный способ сделать вставку идемпотентной. Но при повторном запуске получили ошибку `more than one row returned by a subquery`.

Почему так вышло: `ON CONFLICT DO NOTHING` без указания конкретного constraint срабатывает только при нарушении **существующего** уникального ключа. У таблицы `routes` уникален только `route_id` — а он `SERIAL`, то есть каждый INSERT получает новое значение и никогда не конфликтует. В итоге повторный запуск честно вставил ещё 3 маршрута-дубля, и subquery `SELECT route_id FROM routes WHERE origin = 'HAN' AND destination = 'KUL'` вернул 2 строки вместо одной — отсюда ошибка.

### Решение: WHERE NOT EXISTS + JOIN

Вместо `ON CONFLICT` используем паттерн `INSERT ... SELECT ... WHERE NOT EXISTS`:

```sql
INSERT INTO routes (...)
SELECT * FROM (VALUES (...)) AS v(...)
WHERE NOT EXISTS (
    SELECT 1 FROM routes r WHERE r.origin = v.origin AND r.destination = v.destination
);
```

Для `source_route_mappings` `ON CONFLICT (route_id, source) DO NOTHING` работает корректно — там уникальный ключ `(route_id, source)` уже определён в схеме. Маппинги получаем через `JOIN routes` чтобы не хардкодить route_id (он auto-generated и может различаться между окружениями).

### Урок

`ON CONFLICT DO NOTHING` — не магическая защита от дублей. Он работает только если в таблице есть подходящий уникальный constraint, который реально нарушается при дубле. Всегда проверяй: какой именно constraint должен сработать?

---

## TASK-008 — Pydantic модели: Flight, Route, SourceMapping

**Файлы:** `models/flight.py`, `models/route.py`, `models/__init__.py`

### Почему Decimal, а не float для цены

`float` в Python — IEEE 754 двоичная дробь. `0.1 + 0.2 = 0.30000000000000004`. Для денег это недопустимо: при агрегации и вычислении скидок накапливается погрешность.

`Decimal` — десятичная арифметика с точной репрезентацией. В PostgreSQL соответствующий тип — `NUMERIC`. Pydantic автоматически конвертирует строки и числа в `Decimal` при валидации, поэтому коннекторы могут передавать цену как строку `"105.50"` — модель разберётся сама.

### Timezone-aware datetime: почему это обязательно

Aviasales возвращает время вылета в Bangkok (UTC+7), Trip.com — в UTC, Agoda — иногда без зоны вообще. Если хранить naive datetime (без tzinfo), сравнение `departure_time` между источниками станет некорректным: рейс в 10:00 Bangkok и рейс в 10:00 UTC выглядят одинаково, но это разные рейсы.

Валидатор `must_be_timezone_aware` отклоняет любой naive datetime на уровне модели — ошибка возникает раньше, чем данные попадут в БД. Принцип **fail fast**: лучше `ValidationError` в парсере, чем молча записать некорректное время.

Правило: приводить все datetime к UTC в коннекторе/парсере до создания объекта `Flight`.

### Валидация IATA: field_validator vs Annotated

Можно было написать через `Annotated[str, Field(pattern=r'^[A-Z]{3}$')]` — одна строка. Выбрал `@field_validator` по двум причинам:

1. Сообщение об ошибке информативнее: `"Must be a 3-letter uppercase IATA code, got: 'hanoi'"` vs стандартное `"String should match pattern"`.
2. Один валидатор покрывает оба поля (`origin` и `destination`) через перечисление имён.

### from_attributes=True и совместимость с ORM

`from_attributes=True` в `model_config` разрешает Pydantic читать поля из ORM-объектов через атрибуты (`.column_name`) вместо dict-доступа. Когда будем читать данные из PostgreSQL, можно будет делать `Flight.model_validate(db_row)` напрямую, без ручного маппинга.

### flight_number: Optional[str]

Чартерные и низкобюджетные рейсы иногда не имеют номера рейса. Поле `None` по умолчанию. В уникальном ключе таблицы это решается через `NULLS NOT DISTINCT` (см. TASK-004).

---

## TASK-009 — Pydantic модели: CdcEvent, RawSnapshot

**Файлы:** `models/cdc.py`, `models/storage.py`

### Почему event_type — Literal, а не Enum

Оба варианта технически корректны. Выбор в пользу `Literal["INSERT", "UPDATE", "DELETE"]` обусловлен тремя причинами:

1. **Прямое соответствие БД.** В PostgreSQL поле `event_type` — VARCHAR с CHECK constraint. Строки `"INSERT"/"UPDATE"/"DELETE"` хранятся as-is. Если бы использовали Enum, при чтении из БД нужна явная конвертация строки в Enum. С Literal — Pydantic принимает строку напрямую.
2. **Простота сериализации.** `model.model_dump()` вернёт строку `"UPDATE"`, а не `<EventType.UPDATE: 'UPDATE'>` — можно сразу писать в JSON без кастомных сериализаторов.
3. **Меньше кода.** Enum требует отдельного определения класса. Literal — одна строка в аннотации.

Единственный случай, когда Enum предпочтительнее — если нужно навешивать методы на значения (например, `event.is_price_change()`). Здесь таких требований нет.

### changed_fields: dict[str, dict[str, Any]]

Структура `{"price": {"old": 120.0, "new": 105.0}}` — это намеренно гибкий формат. CDC-движок будет записывать сюда любые изменившиеся поля (не только цену). PostgreSQL хранит это как `JSONB` — индексируемый JSON с поддержкой GIN-индексов для поиска по содержимому.

Дефолт `{}` (пустой dict) для INSERT/DELETE, где нет "до/после" — логичен: если рейс появился впервые, нет "старого" состояния для сравнения.

---

## TASK-010 — Абстрактный базовый класс Connector

**Файл:** `connectors/base.py`

### Template Method Pattern

`BaseConnector` реализует паттерн **Template Method**: публичный метод `fetch()` содержит общий алгоритм (лог старта → вызов → лог результата → обработка ошибки), а подклассы переопределяют только `_fetch()` — конкретную реализацию скрапинга.

Почему `_fetch` с подчёркиванием, а не `fetch` напрямую? Потому что логика оркестрации (логирование, error handling) должна всегда выполняться — если бы коннектор переопределял `fetch()` целиком, он мог бы забыть про catch. Одно подчёркивание сигнализирует: "это internal, переопределяй _fetch, не fetch".

### Async по умолчанию

Все коннекторы используют `async def` — Playwright работает в async контексте, и блокирующий коннектор заморозил бы весь Prefect flow. Даже если конкретный коннектор использует синхронный httpx (без XHR-перехвата), его легко обернуть через `asyncio.to_thread()` внутри `_fetch`.

### Почему fetch возвращает `[]` при ошибке, а не пробрасывает исключение

Pipeline должен быть resilient: если один источник недоступен, остальные должны продолжать работу. Prefect flow итерирует по маппингам и вызывает коннекторы — падение одного не должно прерывать цикл. Ошибка логируется через `logger.exception()` (с полным traceback) для последующего анализа.

---

## TASK-011 — Raw Storage: save_raw и load_raw

**Файлы:** `storage/raw.py`, `models/storage.py`

### Зачем сохранять сырые файлы отдельно от БД

Raw Storage — это страховка. Если парсер сломался или мы изменили логику извлечения данных — не нужно снова запускать браузер и ждать загрузки страницы. Достаточно взять уже сохранённый JSON-файл с диска и перепарсить его с новой логикой.

### Структура файловой системы

```
raw_storage/
  aviasales/
    1/           ← route_id
      20260618T013817_395285.json   ← timestamp в имени = уникальность
    2/
  trip/
    1/
```

Путь `raw_storage/{source}/{route_id}/{timestamp}.json`. Timestamp с микросекундами гарантирует уникальность даже при двух вызовах в одну секунду.

### Почему добавили id в RawSnapshot

Изначально модель `RawSnapshot` не имела `id`. Но `load_raw(snapshot_id: int)` должна искать файл по ID из таблицы `raw_snapshots`. Добавили `id: int | None = None` — поле опциональное при создании объекта (до вставки в БД), заполняется после `RETURNING id`.

### monkeypatch в тестах

Тесты подменяют `RAW_STORAGE_DIR` на временную папку pytest (`tmp_path`) — файлы не засоряют рабочую директорию и автоматически удаляются. БД при этом используется настоящая: тесты проверяют реальную вставку в `raw_snapshots`.

---

## TASK-012 + TASK-013 — Aviasales: от Playwright к Travelpayouts API

**Файлы:** `connectors/aviasales.py`, `parser/aviasales.py`

### Что пробовали и почему не сработало

Изначальный план: запустить Playwright, перехватить XHR с данными о рейсах. При исследовании нашли три слоя защиты:

1. **AWS WAF** — `tickets-api.aviasales.ru/search/v2/start` возвращает **403** любому headless-браузеру. Сайт генерирует fingerprint-токен через `fp.js` и проверяет его на сервере.
2. **WebSocket/Centrifuge** — реальные данные о рейсах приходят не через XHR, а через WebSocket (протокол Centrifuge, библиотека `lib-centrifuge.js`). Даже если бы WAF пропустил — нужно было бы парсить бинарный WebSocket-протокол.
3. **Подловили на рекламе** — единственный крупный JSON который перехватили (~74KB) оказался данными рекламного блока Яндекса в формате JSON:API, а не рейсами.

### Решение: официальный API

Aviasales имеет официальный партнёрский API — **Travelpayouts Data API**. Бесплатная регистрация на travelpayouts.com даёт токен. Те же данные что на сайте, без anti-bot защиты.

Endpoint: `https://api.travelpayouts.com/aviasales/v3/prices_for_dates`

Токен хранится в `.env` как `TRAVELPAYOUTS_TOKEN`. Если не задан — коннектор возвращает `None` без ошибки (graceful degradation).

Это стандартная ситуация в реальных проектах: начали со скрапинга, обнаружили серьёзную защиту, переключились на официальный API.

### Формат ответа Travelpayouts v3

```json
{
  "success": true,
  "data": [
    {
      "origin": "HAN",
      "destination": "KUL",
      "price": 125,
      "airline": "AK",
      "flight_number": "D7535",
      "departure_at": "2026-07-18T10:00:00+07:00",
      "transfers": 0,
      "duration_to": 200
    }
  ],
  "currency": "usd"
}
```

### Как парсим в Flight

- `arrival_time` — в API нет, вычисляем: `departure_time + timedelta(minutes=duration_to)`
- `airline` — только IATA код (`AK` = AirAsia), не полное название. Ограничение API.
- `flight_number` — может быть `None` (чартеры). Поле опциональное в `Flight`.
- Если поле отсутствует или невалидно — item пропускается с `logger.warning`, остальные парсятся.

### fetch_raw vs _fetch: почему два метода

`_fetch()` — контракт BaseConnector, возвращает `list[Flight]`. `fetch_raw()` — публичный метод, возвращает сырой `dict | None`. Разделение позволяет тестировать получение данных и парсинг независимо. `_fetch()` вызывает `fetch_raw()`, сохраняет через `save_raw()`, затем передаёт в `parse_aviasales()`.

---

## TASK-017 — CDC Engine: compare_snapshots

### Ключ сравнения: почему именно эти 4 поля

Ключ `(provider, flight_number, departure_time, route_id)` — минимально достаточный уникальный идентификатор рейса:
- `provider` — разные источники могут вернуть одинаковый рейс, не смешиваем
- `flight_number` — уникален в рамках дня, но не глобально (один рейс летит ежедневно)
- `departure_time` — точный момент вылета, отличает рейсы разных дней
- `route_id` — рейс привязан к нашему маршруту (SVO→LED ≠ LED→SVO)

### Почему scraped_at не входит в сравниваемые поля

`scraped_at` обновляется при каждом запросе. Включить его в `_COMPARE_FIELDS` → каждый snapshot генерирует UPDATE на все рейсы. Мы сравниваем только бизнес-поля: цена, авиакомпания, время прилёта, длительность, пересадки, валюта.

### changed_fields: нативные Python-типы, не строки

В `changed_fields` хранятся `{"old": Decimal("5000"), "new": Decimal("4500")}` — нативные типы из Pydantic модели. Конвертировать в строки здесь нет смысла: CdcEvent принимает `dict[str, dict[str, Any]]`, а сериализация (если нужна) — задача warehouse слоя.

### Функция чистая: нет обращений к БД, нет side effects

`compare_snapshots` — deterministic pure function: те же входные данные → те же события (кроме `occurred_at`, который `datetime.now()`). Это позволяет тестировать без моков и изолированно от остального стека.

---

## TASK-018 — Warehouse Current: apply_cdc_to_current

### Почему используем _UPSERT для INSERT-событий, а не просто INSERT

UNIQUE-ограничение на `(provider, flight_number, departure_time, route_id)` не даст создать дубль, если по какой-то причине INSERT-событие придёт повторно (например, при перезапуске после сбоя без сохранения состояния). `ON CONFLICT DO UPDATE` превращает любой INSERT в идемпотентную операцию. Это защита от "at-least-once" семантики.

### IS NOT DISTINCT FROM для flight_number NULL

`flight_number` в схеме — `VARCHAR(20)` без `NOT NULL` (чартеры). В WHERE нельзя писать `flight_number = %(flight_number)s`, потому что `NULL = NULL` — false в SQL. `IS NOT DISTINCT FROM` корректно обрабатывает NULL: `NULL IS NOT DISTINCT FROM NULL` = true.

### Тест rollback: почему FailingCursor, а не реальная FK-ошибка

Симулировать ошибку через неправильный route_id не надёжно (нужно знать что не существует), а через уникальное нарушение — не отражает "середину пакета". Patch через `FailingCursor` позволяет точно сказать "упасть на N-ом вызове execute" и проверить, что rollback действительно отменил предыдущий execute в той же транзакции.

### Phase 3 завершена

CDC Engine (TASK-017) + Warehouse Current (TASK-018) — ключевая связка: теперь система умеет сравнивать снапшоты и обновлять актуальное состояние в БД.

---

## TASK-019 — Warehouse History: SCD Type 2

### Почему переиспользуем _get_conn, _parse_key, _index, _params из warehouse/current.py

Это одна доменная зона (warehouse) и один DB-драйвер (psycopg2). Дублировать одни и те же утилиты было бы хуже — любое изменение схемы коннекта или формата flight_key пришлось бы менять в двух местах.

### SCD Type 2: как работает UPDATE

"Close + Insert" в одной транзакции:
1. `UPDATE flights_history SET valid_to=now, is_current=false WHERE ... AND is_current=true` — закрываем текущую запись
2. `INSERT INTO flights_history (..., valid_from=now, valid_to=NULL, is_current=true)` — пишем новую

Если шаг 1 не нашёл строку (например, история ещё не была создана) — ничего не упадёт, просто UPDATE не затронет строк. Это допустимо.

### Инвариант: flights_history WHERE is_current=true == flights_current

Тест `test_is_current_history_matches_current_table` проверяет этот инвариант после сложного сценария (INSERT + UPDATE + DELETE). Это самый важный тест в наборе — он доказывает, что `current` и `history` не расходятся.

---

## Архитектурная заметка: хранение данных и retention

### Что сейчас в DWH

`flights_current`, `flights_history`, `cdc_events` — пустые до тех пор, пока не запустится полный пайплайн (Prefect flow, TASK-006 + TASK-021). `raw_snapshots` заполняется только интеграционными тестами.

### Retention по слоям

| Слой | Режим роста | Рекомендуемый retention |
|---|---|---|
| `flights_current` | Постоянный размер (только UPDATE) | Чистка не нужна |
| `flights_history` | +1 строка на каждое изменение цены | 1–2 года |
| `cdc_events` | +1 событие на каждое изменение | 90–180 дней |
| raw файлы + `raw_snapshots` | +1 файл на каждый API-запрос | 7–14 дней |

Raw файлы нужны только для перепарсинга (если был баг в парсере). Через 2 недели — смело удалять. `flights_history` — самое ценное, хранить долго.

### Горизонт планирования

Travelpayouts API отдаёт рейсы **до 12 месяцев вперёд**. Для сезонных поисков (лето, НГ) можно начинать мониторинг за 3–6 месяцев.

### Запрос самого дешёвого билета по маршруту и датам

```sql
SELECT flight_number, airline, price, departure_time
FROM flights_current
WHERE route_id IN (
    SELECT route_id FROM routes
    WHERE origin = 'SVO' AND destination IN ('HAN', 'SGN')
)
  AND departure_time BETWEEN '2026-08-03' AND '2026-08-17'
ORDER BY price ASC
LIMIT 10;
```

Чтобы это заработало: нужно добавить маршруты SVO→HAN, SVO→SGN в `routes` (сейчас засеяны только тестовые HAN→KUL, KUL→CMB, CMB→MOW) и запустить пайплайн.

### Чистка — отдельный Prefect flow

Retention не реализован в текущих задачах. Логичное место — отдельный cron flow (раз в сутки): удаляет raw файлы старше 14 дней, архивирует/удаляет cdc_events старше 180 дней.

---

## TASK-020 — Warehouse Events: save_cdc_events

### Batch insert через execute_values, а не N отдельных INSERT

`psycopg2.extras.execute_values` отправляет все строки одним SQL-запросом: `INSERT INTO ... VALUES (%s,...),(%s,...),(%s,...)`. При 100 событиях это в ~100 раз меньше round-trip'ов к БД и значительно быстрее.

### JSONB-сериализация: почему orjson, а не стандартный json

`changed_fields` может содержать `Decimal` (цена) и `datetime` (arrival_time). Стандартный `json.dumps` бросает `TypeError` на этих типах. `orjson` обрабатывает их нативно; через `default` callback дополнительно покрываем edge cases. Результат декодируем в `str` — psycopg2 с `::jsonb` кастом принимает его и сохраняет как валидный JSONB.

### Что psycopg2 делает с JSONB при чтении

При SELECT psycopg2 автоматически десериализует JSONB обратно в Python dict — никакого `json.loads` вручную не нужно. Тест `test_changed_fields_stored_as_jsonb` проверяет именно это поведение.

---

## TASK-006 — Prefect в Docker Compose

### Почему worker монтирует весь проект и делает pip install при старте

Worker в Prefect 2 запускает flow-код в subprocess на своей же машине (Process work pool). Значит ему нужны все наши Python-пакеты. Два варианта: билдить кастомный Docker image или монтировать директорию + pip install в entrypoint. Второй вариант проще для dev: не нужен Dockerfile, изменения в коде подхватываются без пересборки образа.

### Почему prefect-server использует PostgreSQL как backend, а не SQLite

SQLite (дефолт Prefect) — файловая БД, не подходит для Docker: при рестарте контейнера без volume данные теряются. PostgreSQL у нас уже есть, поэтому используем его. Переменная: `PREFECT_API_DATABASE_CONNECTION_URL=postgresql+asyncpg://...`. Нужен именно `asyncpg` драйвер — Prefect server async.

### Work pool "default-agent-pool" создаётся автоматически

При первом запуске `prefect worker start --pool default-agent-pool` Prefect сам создаёт work pool, если его нет. Не нужно делать `prefect work-pool create` отдельно.

---

## TASK-014 — Trip.com коннектор + парсер

### Архитектура XHR-перехвата: page.on("response", handler)

Playwright позволяет подписаться на все HTTP-ответы страницы. Мы фильтруем по двум критериям:
1. URL содержит `/flights/api/` — это специфичный паттерн Trip.com API, отличающий данные о рейсах от статики, аналитики и т.д.
2. Content-Type содержит `json` — убеждаемся что ответ парсируемый

Первый ответ с `data.flightItineraryList` сохраняется и браузер закрывается. `wait_until="networkidle"` — оптимистичное ожидание, timeout ожидается и обрабатывается через `except`.

### Почему Trip.com не блокирует, а Aviasales блокировал

Aviasales использует AWS WAF + WebSocket (Centrifuge) для доставки данных. Trip.com и Agoda отдают данные через обычные XHR-запросы без агрессивной bot-защиты на уровне JS. Playwright в headless режиме для них достаточен.

### Формат Trip.com XHR-ответа (зафиксированный контракт)

```
data.flightItineraryList[i]:
  priceList[0].adultPrice  → Decimal price
  priceList[0].currency    → "USD"
  flightSegments[0]:
    departureAirportInfo.airportCode → origin IATA
    arrivalAirportInfo.airportCode   → destination IATA
    departureDateTime / arrivalDateTime → "YYYY-MM-DD HH:MM:SS" (UTC-как-есть)
    airlineInfo.airlineName / airlineCode → airline
    flightNumber → str | None
    duration     → минуты
    stopCount    → int
```

Если реальный формат Trip.com изменится — нужно обновить парсер и тесты.

### Datetime без timezone: трактуем как UTC

Trip.com не возвращает timezone в datetime-строках. Для консистентности добавляем `timezone.utc`. Это упрощение — в реальности Trip.com может отдавать local time аэропорта. Для задачи мониторинга цен (а не точного расписания) это приемлемо.

---

## TASK-015 — Agoda коннектор + парсер

### Отличия от Trip.com

| | Trip.com | Agoda |
|---|---|---|
| XHR path | `/flights/api/` | `/api/cronos/flight/` |
| Структура ответа | `data.flightItineraryList[].flightSegments[]` | `data.flights[].legs[]` |
| Datetime формат | `"YYYY-MM-DD HH:MM:SS"` (strptime) | ISO 8601 `"YYYY-MM-DDTHH:MM:SS"` (fromisoformat) |
| Цена | `priceList[0].adultPrice` | `fareAmount` (верхний уровень) |
| Авиакомпания | `airlineInfo.airlineName/airlineCode` | `carrier.name/code` |

Везде один и тот же принцип: берём name, если нет — fallback на code.

### Почему Agoda отдаёт datetime в ISO 8601, а Trip.com — в своём формате

Это особенности конкретных API. Agoda ближе к REST-стандарту (ISO datetime). Trip.com — legacy формат с пробелом вместо `T`. Оба парсятся корректно через `fromisoformat` (Agoda) и `strptime` (Trip.com). Timezone в обоих случаях отсутствует — добавляем `timezone.utc`.

---

## TASK-016 — Search Planner: оркестрация коннекторов

### Что делает `planner/search_planner.py`

`run_search_for_route(route_id)` — асинхронная функция, которая:
1. Читает маршрут из таблицы `routes` по `route_id`
2. Читает только `enabled=true` маппинги из `source_route_mappings`
3. Для каждого маппинга находит коннектор в реестре `_CONNECTOR_REGISTRY` и вызывает `connector.fetch(route, mapping)`
4. Возвращает `dict[str, list[Flight]]` — ключи это имена источников

### Почему raw storage вызывается внутри коннекторов, а не в планнере

Каждый коннектор сам вызывает `save_raw()` в своём `_fetch()`. Это осознанное решение из TASK-012/014/015 — коннектор знает точный момент получения данных и структуру ответа. Планнер не должен знать о формате raw данных: его задача — оркестрировать, а не сохранять.

### Реестр коннекторов `_CONNECTOR_REGISTRY`

Словарь `{source_name: connector_instance}` создаётся на уровне модуля. Если в БД появится маппинг для источника не из реестра — функция пропустит его с `INFO` логом. Добавить новый источник = добавить класс коннектора и одну строку в реестр.

### Почему не используется `asyncio.gather` для параллельных запросов

Планнер запускает коннекторы последовательно (`for mapping in mappings`). Это сделано намеренно на первой итерации — параллельный scraping через Playwright создаёт несколько браузеров одновременно и перегружает систему. Параллелизм можно добавить позже через `asyncio.gather` или семафор.

---

## TASK-021 — Pipeline: полный цикл Search → CDC → Warehouse

### Что делает `scheduler/pipeline.py`

`run_pipeline_for_route(route_id)` — асинхронная функция. Полный цикл за один вызов:

1. **Search Planner** → `{source: [Flight, ...]}` для всех активных источников
2. Для каждого источника:
   - Читает предыдущий снапшот из `flights_current` (`_load_current_flights`)
   - `compare_snapshots(previous, current)` → список CDC событий
   - Если события есть: `apply_cdc_to_current` + `append_history` + `save_cdc_events`
3. Возвращает `PipelineResult` с агрегированной статистикой

### PipelineResult

Pydantic модель:
```python
class PipelineResult(BaseModel):
    route_id: int
    sources_processed: list[str]   # источники, успешно обработанные
    events_count: dict[str, int]   # {"INSERT": N, "UPDATE": N, "DELETE": N}
    duration_seconds: float
    errors: list[str]              # ошибки по источникам (не падают весь pipeline)
```

### Почему warehouse вызывается только при наличии событий

`apply_cdc_to_current`, `append_history`, `save_cdc_events` — все три функции уже проверяют `if not events: return`. Но мы делаем `if events:` в pipeline дополнительно, чтобы избежать открытия транзакции БД вхолостую при повторном запуске без изменений. Три open connection = лишний overhead.

### Устойчивость к ошибкам

Каждый источник обрабатывается в `try/except`. Ошибка в одном источнике (например, Trip.com недоступен) не прерывает обработку других. Ошибка записывается в `PipelineResult.errors` и логируется на уровне `exception` (с traceback). Это важно для мониторинга через Grafana и алертов.

### Первый запуск (нет предыдущего снапшота)

При пустой `flights_current` `_load_current_flights` вернёт `[]`. `compare_snapshots([], current)` создаст INSERT для каждого рейса. Это ожидаемое поведение — первый запуск заполняет таблицу.

---

## Дизайн Telegram Bot: почему умный уведомлятор, а не поисковик

### Два варианта и почему выбрали уведомлятор

**Вариант A (on-demand поисковик):** пользователь пишет маршрут → бот запускает коннекторы прямо сейчас → возвращает результаты. Проблема: нет прямых ссылок на конкретный билет в нашей модели `Flight` (они не сохраняются коннекторами), нужна on-demand оркестрация в обход Prefect, нужна обработка произвольных маршрутов. Слишком большой scope для MVP.

**Вариант B (умный уведомлятор):** pipeline работает по расписанию → CDC фиксирует изменения → бот присылает сообщение только при значимых событиях.

**Ссылка на билет не нужна.** Если мы знаем авиакомпанию, номер рейса, дату и время вылета — найти на Aviasales за 30 секунд. Ценность в том, что система заметила за пользователя, а не в ссылке.

### Почему фиксированный порог max_price — плохая идея

`routes.max_price` — жёсткая константа, которая устаревает, не учитывает сезонность и не отвечает на вопрос "а это вообще дёшево?". Если поставить $200 в январе, летом это может быть нормальной ценой. Руками обновлять неудобно.

**Единственный способ понять что дёшево — сравнение с историей.** У нас есть `flights_history` со всеми наблюдениями. Из него строим rolling average и сравниваем.

### Метод сравнения: rolling average 30 дней

```
baseline = AVG(price) по маршруту за последние 30 дней из flights_history
уведомление = когда current_price < baseline * (1 - PRICE_DROP_THRESHOLD)
```

**PRICE_DROP_THRESHOLD = 0.15** (15%, хранится в `.env`). Система самокалибруется: чем дольше работает, тем точнее baseline. В первые дни мониторинга baseline слабый — это нормально, он дозревает.

Дополнительный триггер: новый исторический минимум за весь период наблюдений (не только 30 дней).

### Мониторинг диапазона дат, а не одной даты

Маршруты уже имеют `date_from` и `date_to`. Коннекторы ищут рейсы по всему диапазону. Это значит: если 5 августа стоит $200, а 6 августа — $138, оба рейса попадут в `flights_history` и при пробитии порога придёт отдельное уведомление с конкретной датой.

Вопрос "а вдруг рядом дешевле?" закрыт самой архитектурой — мы мониторим диапазон.

### Структура уведомления

```
✈️ HAN → KUL  |  6 Aug  |  09:30
VietJet VJ123
💰 $138  (обычно ~$195, −29%)
📉 Новый минимум за 30 дней
```

Дедупликация (TASK-025) отсекает повторные уведомления для одного (route_id, flight_key, rule_type) в течение DEDUP_WINDOW_HOURS (дефолт 4 часа).

---

## TASK-023 — Telegram Bot: send_notification

**Файл:** `notifications/telegram.py`

### Почему функция async

`send_notification` будет вызываться из pipeline (`scheduler/pipeline.py`), который весь async (Prefect + Playwright). Синхронная функция с `asyncio.run()` внутри упала бы с `RuntimeError: This event loop is already running` — нельзя вкладывать event loop в уже запущенный. Поэтому `async def`, вызывается через `await`.

### Почему HTML, а не MarkdownV2

Telegram поддерживает три режима форматирования. MarkdownV2 — самый строгий: символы `-`, `$`, `(`, `)`, `.` нужно экранировать через `\`. Сообщение вида `💰 $138 (−29%)` пришлось бы писать как `💰 \$138 \(\−29%\)`. При автогенерации сообщений с ценами это постоянный источник багов.

HTML (`ParseMode.HTML`) требует экранирования только `<`, `>`, `&` — в наших сообщениях их нет. Выбор очевиден.

### Returns bool, никогда не бросает исключение

Функция возвращает `False` при любой ошибке (нет токена, нет chat_id, TelegramError, неожиданное исключение). Это принципиально: вызывающий код (pipeline) не должен падать из-за недоступного Telegram. Уведомления — вторичная функция, основной цикл сбора данных важнее.

---

## TASK-024 — Движок правил уведомлений

**Файл:** `notifications/rules.py`

### Почему функция должна вызываться ДО записи в warehouse

Это неочевидный, но критичный момент. `_get_historical_min` делает `SELECT MIN(price) FROM flights_history`. Если вызвать `check_notification_rules` уже после того, как `append_history` записала новые рейсы, минимальная цена в таблице будет равна текущей новой цене. `current < hist_min` → `current < current` → False. Правило HISTORICAL_MIN никогда не сработает.

Правильный порядок в pipeline:
```
1. compare_snapshots → events
2. check_notification_rules(event, route, conn)  ← ЗДЕСЬ, до warehouse
3. apply_cdc_to_current / append_history / save_cdc_events
4. send_notification (если trigger не None и should_send вернул True)
```

### Два правила и порядок проверки

**HISTORICAL_MIN** проверяется первым — он важнее. "Цена никогда не была такой низкой" сильнее чем "цена упала на 15%". Если оба правила сработали одновременно (огромный провал), возвращаем HISTORICAL_MIN.

**SIGNIFICANT_DROP** — если новая цена ≥15% ниже rolling average за 30 дней для того же маршрута и источника (не смешиваем Aviasales и Trip.com — у них разная ценовая база).

### Почему нет правила max_price из оригинальной задачи

Обсудили в начале сессии: фиксированный порог устаревает, не учитывает сезонность, требует ручного обновления. Самокалибрующийся rolling average решает ту же задачу без ручного труда. Чем дольше система работает, тем точнее baseline.

### conn как параметр функции

Оригинальная задача задавала сигнатуру `check_notification_rules(event, route) -> ...`. Добавили `conn` — без него невозможно запросить исторические данные. Паттерн передачи соединения снаружи (не создавать внутри функции) — стандарт в этом проекте: проще тестировать через mock, нет скрытых side effects.

---

## TASK-025 — Дедупликация уведомлений

**Файл:** `notifications/dedup.py`

### In-memory vs БД: почему выбрали кэш

Задача допускала оба варианта. Аргументы за in-memory:
- Prefect worker живёт непрерывно в Docker Compose → state сохраняется между запусками pipeline
- Не нужна новая миграция и таблица в БД
- Проще тестировать без реального PostgreSQL

Единственный минус: при рестарте worker'а (например, `docker compose restart prefect-worker`) dedup-кэш сбросится и уведомления за прошедший период могут прийти повторно. Для MVP — приемлемо.

### DEDUP_WINDOW_HOURS читается в runtime, а не на уровне модуля

```python
# Так — НЕ работает с monkeypatch в тестах:
_WINDOW = float(os.getenv("DEDUP_WINDOW_HOURS", "4"))  # читается при import

# Так — работает:
def should_send(...):
    window = float(os.getenv("DEDUP_WINDOW_HOURS", "4"))  # читается при каждом вызове
```

`monkeypatch.setenv` меняет `os.environ` в runtime, но если переменная уже была прочитана при импорте модуля — изменение не увидит. Читаем при каждом вызове функции.

### Тест на истечение окна: backdating вместо freezegun

Чтобы проверить что "через 5 часов уведомление снова разрешено", можно было использовать библиотеку `freezegun` для подмены времени. Вместо этого просто откатываем запись в кэше вручную:

```python
dedup_module._sent_cache[key] = datetime.now(timezone.utc) - timedelta(hours=5)
```

Это работает потому что кэш — публичный dict модуля. Библиотека не нужна, тест понятнее.

### Фикстура autouse для изоляции тестов

```python
@pytest.fixture(autouse=True)
def reset_dedup_cache():
    clear_cache()
    yield
    clear_cache()
```

`autouse=True` — фикстура применяется к каждому тесту в файле автоматически. Без неё тесты зависели бы от порядка запуска: первый вызов `should_send` мог бы "засорить" кэш для следующего теста.

---

## TASK-022 — Prefect Flow: оркестрация маршрутов по расписанию

### Что делает `scheduler/flow.py`

`@flow run_all_routes()` — верхний уровень оркестрации:
1. `_load_enabled_routes()` — читает все `enabled=true` маршруты из БД, сортированные по `priority DESC`
2. Для каждого маршрута вызывает `@task pipeline_task(route_id)` последовательно

`@task pipeline_task(route_id)` — тонкая обёртка над `run_pipeline_for_route`, добавляет:
- retries=1, retry_delay_seconds=30 (автоматический retry при сбое)
- Логирование через стандартный logger

### Почему `logging.getLogger` вместо `get_run_logger()`

`get_run_logger()` требует активный Prefect контекст (FlowRunContext/TaskRunContext). При вызове `.fn()` в юнит-тестах контекста нет → `MissingContextError`. Переключение на стандартный `logging.getLogger(__name__)` позволяет:
- Тестировать функции через `.fn()` без Prefect сервера
- Логи всё равно видны в терминале (и в Prefect UI через `log_prints=True` на flow)

### Тестирование через `.fn()`

В Prefect 3, `@flow` и `@task` объекты имеют атрибут `.fn` — это исходная Python функция без Prefect-инструментации. `prefect_test_harness` из Prefect 2 несовместим с Prefect 3.7.

### `scheduler/deploy.py`

Скрипт деплоя: читает `POLL_INTERVAL_MINUTES` (default 60) и строит cron-выражение `*/N * * * *`. Деплоит flow на пул `default-agent-pool`, который уже настроен в docker-compose. Запускается один раз с хоста:

```bash
PREFECT_API_URL=http://localhost:4200/api python scheduler/deploy.py
```

---

## Grafana: `source` vs `provider` в flights_history

При написании SQL для time series панели использовалось `source AS metric` — но в таблице `flights_history` нет колонки `source`. Колонка называется `provider` (это имя коннектора: aviasales, trip, agoda).

Ошибка проявилась как `Status 500: column "source" does not exist` в Grafana Inspect. Фикс: `provider AS metric` в `price_history.json`.

**Почему `provider`, а не `source`:** В модели `Flight` поле называется `provider` (кто предоставил данные). В `flights_current` и `flights_history` оно хранится как `provider`. Слово `source` используется в контексте коннектора (`source_name`), маппингов (`source_route_mappings`) и raw storage — но не в самих таблицах рейсов.

---

## Безопасность: .env vs .env.example

`.env.example` — публичный шаблон, коммитится в git. Реальные значения только в `.env` (в `.gitignore`).

В этой сессии токен Travelpayouts случайно попал в `.env.example`. Был сразу заменён на `your_token_here`. Правило: в `.env.example` всегда `your_X_here` или `changeme`, никогда реальные значения.

---

## Travelpayouts API: формат даты в запросе

`prices_for_dates` — это кэш дешёвых цен, а не live-поиск. Конкретная дата (`2026-07-01`) возвращает пустой ответ если в кэше нет данных именно на этот день. Формат месяца (`2026-07`) возвращает топ-N дешёвых вариантов за весь месяц — это то что нам нужно.

Фикс в `connectors/aviasales.py`: `search_date.strftime("%Y-%m")` вместо `"%Y-%m-%d"`.

---

## Как запустить и потрогать проект руками

### Запуск инфраструктуры

```bash
docker compose up -d postgres grafana prometheus
# Prefect опционально, нужен только для scheduled runs:
docker compose up -d prefect-server prefect-worker
```

### Открыть UI

| Сервис | URL | Логин |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Prefect | http://localhost:4200 | — |

В Grafana → **Dashboards**: "Price History" (dropdown маршрутов) и "Overview" (топ-5 + CDC + коннекторы).

### Запустить pipeline вручную

```bash
# Активировать venv
source .venv/bin/activate

# Запустить pipeline для маршрута 1 (HAN→KUL)
python -c "import asyncio; from scheduler.pipeline import run_pipeline_for_route; asyncio.run(run_pipeline_for_route(1))"

# Проверить результат
docker compose exec postgres psql -U flight_user -d flight_monitor -c "SELECT COUNT(*) FROM flights_current; SELECT COUNT(*) FROM cdc_events;"
```

После первого запуска `flights_current` заполнится рейсами и Grafana Price History оживёт.

### Состояние DWH после разработки

- `routes` — 3 маршрута: HAN→KUL (prio 90), CMB→MOW (prio 80), KUL→CMB (prio 70)
- `source_route_mappings` — 9 записей (3 маршрута × 3 источника)
- `raw_snapshots` — 27 записей от тестовых запусков (один реальный: aviasales route 1, 42 рейса)
- `flights_current`, `flights_history`, `cdc_events` — пустые, заполнятся после первого запуска pipeline

### Как работает CDC (объяснение)

CDC — это алгоритм diff двух списков рейсов.

**Первый запуск:** `previous = []`, `current = [42 рейса]` → 42 события INSERT → все попадают в `flights_current` и `flights_history`.

**Следующий запуск (через час):** `previous` берётся из `flights_current` (что было). `current` — свежий ответ коннектора. `compare_snapshots` делает diff по ключу `(provider, flight_number, departure_time, route_id)`:
- Рейс есть только в `current` → INSERT
- Рейс есть в обоих, поля изменились → UPDATE с `changed_fields = {field: {old, new}}`
- Рейс есть только в `previous` → DELETE

CDC — чистая функция (`cdc/engine.py`): принимает два списка, возвращает события. Не трогает БД. Это позволяет:
- Тестировать без Docker
- Перепарсить старый raw-файл и прогнать через CDC заново
- Легко отлаживать — виден точный diff

После CDC warehouse-функции (`warehouse/current.py`, `history.py`, `events.py`) применяют события в БД. Уведомления проверяются **до** записи в warehouse — иначе новый минимум сам себя не обнаружит (он уже будет в `flights_history`).

---

## TASK-028 + TASK-029 — Grafana Overview и Prometheus метрики

### TASK-028: дашборд Overview

Три панели: `table` (топ-5 предложений из `flights_current`), `barchart` (CDC события по типам за 24ч из `cdc_events`), `barchart` (запросы по источникам из `raw_snapshots`).

Grafana автоматически подхватила новый `overview.json` через провайдер (`updateIntervalSeconds: 30`) — не нужно было перезапускать контейнер.

В bar chart CDC-панели используется color override по имени серии (`INSERT`=green, `UPDATE`=blue, `DELETE`=red) — это стандартный механизм Grafana overrides, работает когда серии имеют предсказуемые имена.

### TASK-029: Prometheus метрики

Файл `metrics/prometheus.py` — единое место определения всех метрик. Важный паттерн: метрики определяются на уровне модуля (при импорте), а не внутри функций. Это стандарт prometheus_client — если создать Counter дважды с одним именем, библиотека выбросит исключение.

**`_server_started` флаг**: `start_http_server()` нельзя вызвать дважды — это OSError. Флаг нужен потому что `run_all_routes` — это Prefect flow, и в одном worker-процессе flow может запускаться много раз. Без флага каждый запуск пытался бы занять порт.

**Интеграция в pipeline.py**:
- `connector_flights_found` устанавливается сразу после получения результата от коннектора (Gauge — текущее состояние)
- `connector_requests_total` инкрементируется в конце source-блока: success или error (Counter — накопительно)
- `cdc_events_total` инкрементируется внутри цикла по events
- `pipeline_duration_seconds` обсервируется после цикла по источникам с полной длительностью pipeline

**`pipeline_duration_seconds` — Histogram, не Summary**: Histogram позволяет агрегировать по нескольким инстансам и вычислять квантили в Prometheus. Summary считает квантили локально и не агрегируется. Для pipeline-метрики Histogram правильный выбор.

---

## TASK-027 — Grafana дашборд: история цен

### Что добавили

Два файла:
- `dashboard/provisioning/dashboards/provider.yaml` — регистрирует провайдер: говорит Grafana "смотри JSON-дашборды в этой же директории"
- `dashboard/provisioning/dashboards/price_history.json` — дашборд "Price History" с тремя панелями

### Как устроен provisioning дашбордов

Grafana читает `provisioning/dashboards/*.yaml` при старте. Каждый YAML описывает "провайдер" — источник дашбордов. Провайдер типа `file` говорит "ищи JSON-файлы по этому пути и загружай их как дашборды". Мы указали `path: /etc/grafana/provisioning/dashboards` — тот же каталог, где лежат и YAML и JSON. Это самый простой вариант: всё в одном месте.

### Переменная маршрута (template variable)

Dropdown маршрутов реализован через Grafana template variable типа `query`. Запрос:
```sql
SELECT origin || ' → ' || destination AS __text, route_id::text AS __value
FROM routes WHERE enabled = true ORDER BY priority
```
`__text` — то, что видит пользователь в dropdown. `__value` — то, что подставляется в запросы панелей как `$route_id`.

### Почему `price::float`

Колонка `price` в БД типа `NUMERIC` (Decimal). Grafana PostgreSQL datasource возвращает NUMERIC как строку, а не число — тогда time series панель не может построить график. Приведение `price::float` конвертирует в float8 и Grafana корректно строит числовую ось.

### `allowUiUpdates: false` в провайдере

Запрещает сохранять изменения дашборда через UI обратно в файл. Если разрешить (`true`), Grafana будет перезаписывать JSON-файл — это нарушает идею "дашборд как код". При `false` кнопка "Save" в UI показывает предупреждение, но дашборд продолжает работать.

---

## TASK-026 — Grafana PostgreSQL datasource через provisioning

### Что добавили

`dashboard/provisioning/datasources/postgres.yaml` — YAML-файл, который Grafana автоматически читает при старте и создаёт datasource без ручной настройки. Это "provisioning" механизм Grafana — всё через код, ничего через UI.

### Нетривиальный момент: `POSTGRES_HOST=postgres`, а не `localhost`

В `.env` файле `POSTGRES_HOST=localhost` — это для запуска Python-кода на хостовой машине. Но Grafana работает внутри Docker и не видит `localhost` как PostgreSQL. Внутри Docker Compose все сервисы общаются по имени сервиса — `postgres`.

Решение: в `docker-compose.yml` для grafana-сервиса переопределяем переменную:
```yaml
environment:
  POSTGRES_HOST: postgres  # Docker service name, overrides .env value
```

Это значение попадает в YAML через `${POSTGRES_HOST}`. Grafana подставляет переменные окружения в provisioning-файлы автоматически.

### Почему `editable: false`

Datasource помечен `editable: false` — это запрещает изменять его через UI. Если пользователь что-то поменяет вручную, при следующем рестарте Grafana перезапишет конфиг из YAML. `editable: false` сразу делает кнопку "Save" неактивной — меньше путаницы.

---

## TASK-007 — Grafana и Prometheus в Docker Compose

### Что добавили

В `docker-compose.yml` появились два новых сервиса: `grafana` (порт 3000) и `prometheus` (порт 9090). Оба зависят от `postgres` через `condition: service_healthy`.

### Нетривиальные моменты

**Два отдельных volume.** Grafana хранит дашборды в `/var/lib/grafana`, Prometheus — TSDB (time series database) в `/prometheus`. Оба volume именованные (`grafana_data`, `prometheus_data`) — данные переживают `docker compose down`.

**prometheus.yml смонтирован как `:ro`.** Конфиг Prometheus монтируется read-only — сам Prometheus не должен его менять. Если забыть флаг `ro`, Docker смонтирует volume как read-write и изменения в файле на хосте не будут видны после рестарта (Docker может создать анонимный volume поверх).

**`host.docker.internal` в prometheus.yml.** Target для scrape метрик приложения указан как `host.docker.internal:8000` — это DNS-имя, которое Docker на Mac/Windows резолвит в хостовую машину. На Linux нужно либо `--add-host=host.docker.internal:host-gateway`, либо указать IP хоста вручную.

**Grafana provisioning.** Директория `./dashboard/provisioning` монтируется в `/etc/grafana/provisioning`. Это стандартный механизм Grafana для автоматической загрузки datasource и дашбордов при старте — следующие задачи (TASK-026, 027, 028) используют именно его.

**`GF_SECURITY_ADMIN_PASSWORD`.** Пароль вынесен в `.env` через `GRAFANA_PASSWORD` (default `admin`). Grafana не стартует без пароля при первом запуске.
