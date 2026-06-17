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

**Следующая задача:** TASK-002 — Docker Compose: PostgreSQL

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
| critical | 14 | 1 |
| high | 10 | 0 |
| medium | 4 | 0 |
| low | 1 | 0 |
| **Итого** | **29** | **1** |

---

## История сессий

<!-- Каждый агент добавляет запись сюда после завершения задачи -->

| Дата | Задача | Результат |
|---|---|---|
| 2026-06-17 | — | PRD и tasks.json созданы, проект инициализирован |
| 2026-06-17 | TASK-001 | Структура директорий, pyproject.toml, .env.example, .gitignore созданы; pip install -e . успешен |

---

## Инструкция для агента при старте сессии

1. Прочитай `tasks.json` и `PRD_flight_price_final.md`
2. Выбери ОДНУ задачу: `status=pending` + максимальный приоритет + все `dependencies` имеют `status=done`
3. Обнови этот файл — укажи активную задачу в разделе "Текущий трек"
4. Выполни задачу согласно `agent_instructions` из `tasks.json`
5. После завершения: обнови `status` в `tasks.json`, добавь запись в "История сессий"
