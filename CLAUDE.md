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
| Оркестрация | Prefect 2 |
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
| `scheduler/` | Prefect flows |

## Важные решения

- **Connectors не парсят HTML** — только перехватывают XHR запросы через Playwright
- **Aviasales — исключение**: использует AWS WAF + WebSocket/Centrifuge, Playwright блокируется. Вместо скрапинга — **Travelpayouts API** (httpx). Токен: `TRAVELPAYOUTS_TOKEN` в `.env`. Подробнее: `docs/notes.md` секция TASK-012/013.
- **Trip.com и Agoda** — Playwright XHR-перехват (нет official API, нет WAF уровня Aviasales)
- **CDC — pure function** — engine.py не обращается к БД, только сравнивает списки
- **Raw Storage всегда сохраняется** — можно перепарсить без повторного запроса
- **source_route_mappings** — каждый источник может использовать свои коды аэропортов
- **SCD Type 2 в flights_history** — история никогда не удаляется, только добавляется
