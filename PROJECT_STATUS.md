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

**Следующая задача:** TASK-016 — Search Planner (critical)

**Блокеры:** нет

---

## Прогресс по фазам

| Фаза | Описание | Статус |
|---|---|---|
| Phase 1 | Infrastructure (Docker, PostgreSQL, Prefect, Grafana) | done (TASK-006 выполнен, Grafana — позже) |
| Phase 2 | Aviasales connector + Raw Storage | done (TASK-008..013) |
| Phase 3 | CDC Engine + Warehouse | done (TASK-017..020) |
| Phase 4 | Trip.com + Agoda connectors + Orchestration | not started |
| Phase 5 | Notifications + Analytics | not started |

---

## Статистика задач

| Приоритет | Всего | Done |
|---|---|---|
| critical | 14 | 12 |
| high | 10 | 4 |
| medium | 4 | 0 |
| low | 1 | 0 |
| **Итого** | **29** | **18** |

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
| 2026-06-18 | TASK-019 | warehouse/history.py создан; append_history — SCD Type 2; INSERT добавляет, UPDATE закрывает+добавляет, DELETE закрывает; 8/8 тестов passed |
| 2026-06-18 | TASK-020 | warehouse/events.py создан; save_cdc_events — batch insert через execute_values; changed_fields как JSONB через orjson; 6/6 тестов passed |
| 2026-06-18 | TASK-006 | prefect-server + prefect-worker добавлены в docker-compose.yml; UI на :4200 доступен; worker подключён, work pool создан |
| 2026-06-18 | TASK-014 | connectors/trip.py (Playwright XHR-перехват /flights/api/); parser/trip.py (data.flightItineraryList); 12 unit тестов парсера, 25/25 общий |
| 2026-06-18 | TASK-015 | connectors/agoda.py (Playwright XHR /api/cronos/flight/); parser/agoda.py (data.flights + legs); 12 unit тестов, 37/37 общий |

---

## Инструкция для агента при старте сессии

1. Прочитай `tasks.json` и `PRD_flight_price_final.md`
2. Выбери ОДНУ задачу: `status=pending` + максимальный приоритет + все `dependencies` имеют `status=done`
3. Обнови этот файл — укажи активную задачу в разделе "Текущий трек"
4. Выполни задачу согласно `agent_instructions` из `tasks.json`
5. После завершения: обнови `status` в `tasks.json`, добавь запись в "История сессий"
