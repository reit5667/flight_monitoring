# PROJECT STATUS — Flight Price Intelligence Platform

## Документы проекта

| Файл | Описание |
|---|---|
| `PRD_flight_price_final.md` | Финальный PRD — требования, архитектура, модель данных |
| `tasks.json` | Список задач для агентов (29 задач) |
| `PROJECT_STATUS.md` | Этот файл — текущий трек и история |

---

## Текущий трек

**Активная задача:** нет

**Следующая задача:** TASK-019 — Warehouse History (critical)

**Блокеры:** нет

---

## Прогресс по фазам

| Фаза | Описание | Статус |
|---|---|---|
| Phase 1 | Infrastructure (Docker, PostgreSQL, Prefect, Grafana) | partial (Prefect — TASK-006 pending) |
| Phase 2 | Aviasales connector + Raw Storage | done (TASK-008..013) |
| Phase 3 | CDC Engine | done (TASK-017) |
| Phase 4 | Trip.com + Agoda connectors + Orchestration | not started |
| Phase 5 | Notifications + Analytics | not started |

---

## Статистика задач

| Приоритет | Всего | Done |
|---|---|---|
| critical | 14 | 10 |
| high | 10 | 1 |
| medium | 4 | 0 |
| low | 1 | 0 |
| **Итого** | **29** | **13** |

---

## История сессий

<!-- Каждый агент добавляет запись сюда после завершения задачи -->

| Дата | Задача | Результат |
|---|---|---|
| 2026-06-17 | — | PRD и tasks.json созданы, проект инициализирован |
| 2026-06-17 | TASK-001 | Структура директорий, pyproject.toml, .env.example, .gitignore созданы; pip install -e . успешен |
| 2026-06-17 | TASK-002 | docker-compose.yml создан; postgres:16 поднят healthy, psql соединение проверено, persistence после down/up подтверждена |
| 2026-06-17 | TASK-003 | migrations/001_routes.sql создан; таблицы routes и source_route_mappings применены, идемпотентность проверена |
| 2026-06-18 | TASK-004 | migrations/002_warehouse.sql создан; 4 таблицы применены, CHECK constraint на event_type проверен |
| 2026-06-18 | TASK-005 | migrations/003_seed_routes.sql создан; 3 маршрута + 9 маппингов, идемпотентность через WHERE NOT EXISTS проверена |
| 2026-06-18 | TASK-008 | models/flight.py + models/route.py созданы; 11/11 тестов passed; venv настроен |
| 2026-06-18 | TASK-009 | models/cdc.py + models/storage.py созданы; 19/19 тестов passed |
| 2026-06-18 | TASK-010 | connectors/base.py создан (Template Method, async); 23/23 тестов passed |
| 2026-06-18 | TASK-011 | storage/raw.py создан (save_raw + load_raw); models/storage.py: добавлен id; 7/7 тестов passed |
| 2026-06-18 | TASK-012 | connectors/aviasales.py создан; переключён на Travelpayouts API (WAF блокировал Playwright); 6 unit тестов |
| 2026-06-18 | TASK-013 | parser/aviasales.py создан; parse_aviasales → list[Flight]; 13 тестов; arrival_time = departure + duration |
| 2026-06-18 | TASK-017 | cdc/engine.py создан; compare_snapshots — pure function; ключ (provider, flight_number, departure_time, route_id); 17/17 тестов passed |
| 2026-06-18 | TASK-018 | warehouse/current.py создан; apply_cdc_to_current — INSERT/UPDATE/DELETE + upsert; транзакция; rollback при ошибке; 10/10 тестов passed |

---

## Инструкция для агента при старте сессии

1. Прочитай `tasks.json` и `PRD_flight_price_final.md`
2. Выбери ОДНУ задачу: `status=pending` + максимальный приоритет + все `dependencies` имеют `status=done`
3. Обнови этот файл — укажи активную задачу в разделе "Текущий трек"
4. Выполни задачу согласно `agent_instructions` из `tasks.json`
5. После завершения: обнови `status` в `tasks.json`, добавь запись в "История сессий"
