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

**Следующая задача:** TASK-011 (проверить зависимости)

**Блокеры:** нет

---

## Прогресс по фазам

| Фаза | Описание | Статус |
|---|---|---|
| Phase 1 | Infrastructure (Docker, PostgreSQL, Prefect, Grafana) | not started |
| Phase 2 | Aviasales connector + Raw Storage | not started |
| Phase 3 | CDC Engine | not started |
| Phase 4 | Trip.com + Agoda connectors + Orchestration | not started |
| Phase 5 | Notifications + Analytics | not started |

---

## Статистика задач

| Приоритет | Всего | Done |
|---|---|---|
| critical | 14 | 7 |
| high | 10 | 1 |
| medium | 4 | 0 |
| low | 1 | 0 |
| **Итого** | **29** | **8** |

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

---

## Инструкция для агента при старте сессии

1. Прочитай `tasks.json` и `PRD_flight_price_final.md`
2. Выбери ОДНУ задачу: `status=pending` + максимальный приоритет + все `dependencies` имеют `status=done`
3. Обнови этот файл — укажи активную задачу в разделе "Текущий трек"
4. Выполни задачу согласно `agent_instructions` из `tasks.json`
5. После завершения: обнови `status` в `tasks.json`, добавь запись в "История сессий"
