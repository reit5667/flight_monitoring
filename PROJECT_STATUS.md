# PROJECT STATUS — Flight Price Intelligence Platform

## Документы проекта

| Файл | Описание |
|---|---|
| `PRD_flight_price_final.md` | Финальный PRD — требования, архитектура, модель данных |
| `tasks.json` | Список задач для агентов (39 задач) |
| `PROJECT_STATUS.md` | Этот файл — текущий трек и история |

---

## Текущий трек

**Активная задача:** нет (сессия завершена)

**Следующая задача:** TASK-037 — inline-автодополнение города при вводе маршрута

**Блокеры:** нет

---

## Прогресс по фазам

| Фаза | Описание | Статус |
|---|---|---|
| Phase 1 | Infrastructure (Docker, PostgreSQL, Prefect, Grafana) | done |
| Phase 2 | Aviasales connector + Raw Storage | done |
| Phase 3 | CDC Engine + Warehouse | done |
| Phase 4 | Trip.com + Agoda connectors + Orchestration | done |
| Phase 5 | Notifications + Analytics | **done** (TASK-023..029) |
| Refactor | Удалён Agoda, `db.py`, уведомления подключены | **done** |

---

## Статистика задач

| Приоритет | Всего | Done |
|---|---|---|
| critical | 14 | 14 |
| high | 12 | 12 |
| medium | 7 | 5 |
| low | 3 | 2 |
| **Итого** | **36** | **33** |

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
| 2026-06-18 | TASK-016 | planner/search_planner.py создан; run_search_for_route читает маршрут+маппинги из БД, запускает коннекторы; 6/6 unit тестов |
| 2026-06-18 | TASK-021 | scheduler/pipeline.py создан; run_pipeline_for_route — полный цикл: Search→CDC→Warehouse; PipelineResult с events_count и errors; 6/6 unit тестов |
| 2026-06-18 | TASK-022 | scheduler/flow.py (Prefect @flow + @task); scheduler/deploy.py (деплой с cron по POLL_INTERVAL_MINUTES); 5/5 unit тестов; .fn() вместо test harness (несовместим с Prefect 3) |
| 2026-06-18 | TASK-023 | notifications/telegram.py; async send_notification → bool; ParseMode.HTML (не MarkdownV2 — экранирование мешало бы ценам); 5/5 тестов; .env.example: PRICE_DROP_THRESHOLD_PCT=15 |
| 2026-06-18 | TASK-024 | notifications/rules.py; NotificationTrigger (Pydantic); 2 правила: HISTORICAL_MIN (приоритет) + SIGNIFICANT_DROP (rolling avg 30 дней, 15%); вызывать ДО warehouse write; 8 тестов → 13/13 total |
| 2026-06-18 | TASK-025 | notifications/dedup.py; in-memory dict (worker живёт постоянно → state сохраняется); DEDUP_WINDOW_HOURS читается в runtime (monkeypatch); backdating cache в тестах вместо freezegun; 5 тестов → 18/18 total |
| 2026-06-18 | TASK-007 | grafana/grafana:10.4.2 + prom/prometheus:v2.51.0 добавлены в docker-compose.yml; prometheus.yml создан; grafana_data + prometheus_data volumes; оба UI доступны; GRAFANA_PASSWORD в .env.example |
| 2026-06-18 | TASK-026 | dashboard/provisioning/datasources/postgres.yaml; POSTGRES_HOST=postgres в grafana env (Docker service name, не localhost); health check: "Database Connection OK"; SELECT COUNT(*) FROM routes = 3 |
| 2026-06-18 | TASK-027 | provider.yaml + price_history.json; 3 панели: timeseries (история цен), stat (min всё время), stat (avg 7 дней); dropdown маршрутов из routes; дашборд "Price History" загружен в Grafana |
| 2026-06-18 | TASK-028 | overview.json; 3 панели: table (топ-5 из flights_current), barchart (CDC события 24ч по типам), barchart (запросы по источникам из raw_snapshots); дашборд "Overview" загружен в Grafana |
| 2026-06-18 | TASK-029 | metrics/prometheus.py: 4 метрики (counter ×2, histogram, gauge); start_metrics_server() в flow.py; метрики интегрированы в pipeline.py; Prometheus scrape подтверждён через API |
| 2026-06-18 | fixes | Aviasales: формат даты %Y-%m вместо %Y-%m-%d; Grafana price_history: source→provider в flights_history; первый реальный прогон pipeline: 10 рейсов HAN→KUL, от $92 (AirAsia) |
| 2026-06-18 | TASK-030 + refactor | Agoda удалён (коннектор, парсер, тесты, DB mappings); _get_conn() → db.py (единое место); уведомления подключены в pipeline.py (BEFORE warehouse write); Trip.com WAF 432 — known limitation; 138/138 тестов |
| 2026-06-27 | TASK-031..034 | Закрыты как done (уже были реализованы): ReplyKeyboard, выбор пассажиров, история цен со sparkline, подписки |
| 2026-06-27 | TASK-035 | bot/airports.py: словарь 120+ аэропортов IATA→название, обратный индекс (рус/англ), route_label(), parse_route_input(); кнопки маршрутов теперь показывают читаемые названия; свободный ввод принимает 'Ханой Бангкок', 'Hanoi Bangkok', 'HAN BKK' |
| 2026-06-27 | TASK-036 | Гибкий поиск за месяц: кнопка "📅 Весь [месяц]" в календаре; cb_cheapest — топ-3 дешёвых даты с ценами, длительностью, авиакомпанией; кнопка переключения на следующий месяц прямо из результатов |

---

## Инструкция для агента при старте сессии

1. Прочитай `tasks.json` и `PRD_flight_price_final.md`
2. Выбери ОДНУ задачу: `status=pending` + максимальный приоритет + все `dependencies` имеют `status=done`
3. Обнови этот файл — укажи активную задачу в разделе "Текущий трек"
4. Выполни задачу согласно `agent_instructions` из `tasks.json`
5. После завершения: обнови `status` в `tasks.json`, добавь запись в "История сессий"
