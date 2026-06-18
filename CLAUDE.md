# Flight Monitor — инструкции для Claude

## Что это за проект

Flight Price Intelligence Platform — система мониторинга цен на авиабилеты.
Полный PRD: `PRD_flight_price_final.md`. Читай его только когда нужна конкретная деталь.

## Как начинать каждую сессию

1. Прочитай `PROJECT_STATUS.md` — там активная задача и история
2. Прочитай нужные задачи из `tasks.json` (только те, что предстоит делать)
3. Выбери ONE задачу: `status=pending`, наивысший приоритет, все dependencies — `done`
4. Обнови `PROJECT_STATUS.md` — укажи задачу в "Активная задача"
5. Объясни пользователю что берёшь в работу и почему именно эту задачу

## Как заканчивать каждую сессию

1. Обнови `status` в `tasks.json` (только `done` если прошли все test_steps)
2. Обнови `PROJECT_STATUS.md` — активная задача, статистика, запись в истории
3. Обнови `CLAUDE.md` если что-то изменилось в архитектуре или подходе
4. Обнови memory-файл проекта (`~/.claude/projects/.../memory/project_flight_monitor.md`)
5. Обнови `docs/notes.md` — по каждой выполненной задаче: нетривиальные решения, проблемы и почему выбрали именно этот подход

## Стек

| Компонент | Решение |
|---|---|
| Язык | Python 3.12+ |
| Browser automation | Playwright (XHR-перехват, не HTML-парсинг) |
| HTTP-клиент | httpx |
| JSON | orjson |
| Валидация | Pydantic v2 |
| БД | PostgreSQL 16 |
| Оркестрация | Prefect 2 (docker) / Prefect 3.7 (venv локально) |
| Контейнеризация | Docker Compose |
| Мониторинг | Prometheus + Grafana |
| Уведомления | python-telegram-bot |

## Архитектура (кратко)

```
Prefect Scheduler
    → Search Planner (читает маршруты из БД)
        → Connectors (Aviasales / Trip / Agoda)
            → Raw Storage (JSON файлы)
                → Parsers (JSON → Flight objects)
                    → CDC Engine (сравнивает с предыдущим snapshot)
                        → PostgreSQL (flights_current, flights_history, cdc_events)
                            → Grafana (аналитика)
                            → Telegram Bot (уведомления)
```

Подробное объяснение на русском: `docs/HOW_IT_WORKS.md`

## Ключевые файлы

| Файл | Назначение |
|---|---|
| `tasks.json` | 29 задач с acceptance criteria и test_steps |
| `PROJECT_STATUS.md` | Текущий трек, история сессий |
| `migrations/` | SQL миграции (применяются через docker compose) |
| `models/` | Pydantic модели (Flight, Route, CdcEvent и др.) |
| `connectors/` | Один файл на источник, все наследуют BaseConnector |
| `parser/` | Один файл на источник, raw JSON → list[Flight] |
| `cdc/engine.py` | Чистая функция: compare_snapshots → list[CdcEvent] |
| `warehouse/` | Запись в БД (current, history, events) |
| `planner/search_planner.py` | Оркестрация коннекторов для маршрута → dict[source, list[Flight]] |
| `scheduler/pipeline.py` | Полный цикл для маршрута: Search → CDC → Warehouse → PipelineResult |
| `scheduler/flow.py` | Prefect @flow + @task; деплой через scheduler/deploy.py |

## Важные решения

- **Connectors не парсят HTML** — только перехватывают XHR запросы через Playwright
- **Aviasales — исключение**: использует AWS WAF + WebSocket/Centrifuge, Playwright блокируется. Вместо скрапинга — **Travelpayouts API** (httpx). Токен: `TRAVELPAYOUTS_TOKEN` в `.env`. Подробнее: `docs/notes.md` секция TASK-012/013.
- **Trip.com XHR-паттерн**: `/flights/api/` → `data.flightItineraryList`
- **Agoda XHR-паттерн**: `/api/cronos/flight/` → `data.flights`
- **CDC — pure function** — engine.py не обращается к БД, только сравнивает списки
- **Warehouse — три функции**: `apply_cdc_to_current` (flights_current), `append_history` (SCD Type 2), `save_cdc_events` (batch insert)
- **Raw Storage всегда сохраняется** — можно перепарсить без повторного запроса
- **source_route_mappings** — каждый источник может использовать свои коды аэропортов
- **SCD Type 2 в flights_history** — история никогда не удаляется, только добавляется
- **Prefect worker** — монтирует код проекта через volume + pip install в entrypoint; PostgreSQL как backend сервера (не SQLite)
- **Prefect версии расходятся** — venv локально имеет Prefect 3.7, docker image — Prefect 2. `prefect_test_harness` не работает в v3; тесты flow вызываются через `.fn()`. `get_run_logger()` требует Prefect контекст — в flow.py используется стандартный `logging.getLogger`
- **Search Planner** — коннекторы запускаются последовательно (не параллельно): Playwright создаёт тяжёлые браузерные процессы, параллельный запуск перегружает систему
- **Pipeline устойчив к ошибкам** — ошибка в одном источнике не прерывает другие; фиксируется в `PipelineResult.errors`
