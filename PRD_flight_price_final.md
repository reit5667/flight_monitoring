# Flight Price Intelligence Platform
## PRD v1.0 — 2026-06-17

---

## 1. Обзор и цели

### Цель проекта

Разработать платформу мониторинга цен на авиабилеты, которая регулярно собирает предложения с нескольких агрегаторов, отслеживает изменения стоимости с помощью собственного CDC-движка (Change Data Capture), хранит историю изменений и предоставляет аналитику и уведомления.

### Двойная ценность проекта

1. **Практическая** — личный инструмент для поиска дешёвых авиабилетов по конкретным маршрутам.
2. **Портфолио Data Engineering** — демонстрация полного цикла обработки данных:
   - ETL/ELT
   - CDC (Change Data Capture)
   - Data Warehouse
   - Data Modeling (SCD Type 2)
   - Pipeline Orchestration
   - Observability
   - Containerization

---

## 2. Целевая аудитория

### v1 — Личное использование

- Единственный пользователь — автор проекта.
- Маршруты задаются вручную через конфигурацию.
- Уведомления приходят в личный Telegram.

### v2 — Публичный доступ (будущее)

- Telegram-бот с подпиской для широкой аудитории.
- Пользователи самостоятельно добавляют маршруты через бот.
- Монетизация через небольшую ежемесячную подписку.

---

## 3. Основная идея — самостоятельный CDC

Внешние сайты не предоставляют поток изменений.

Система самостоятельно строит CDC, сравнивая два последовательных snapshot'а результатов поиска:

```
10:00  →  AirAsia: 120 USD
11:00  →  AirAsia: 105 USD
↓
CDC Event: UPDATE price: 120 → 105
```

Таким образом создаётся полноценный поток событий: `INSERT` / `UPDATE` / `DELETE`

---

## 4. Основные функции

### 4.1 Сбор данных (Connectors)

**Описание:** Каждый коннектор обращается к внутреннему JSON API сайта (XHR), возвращает список предложений в единой модели `Flight`. Playwright используется только для получения необходимых токенов/cookies и обхода динамического интерфейса — не для парсинга HTML.

**Acceptance criteria:**
- Connector возвращает список объектов `Flight` с полностью заполненными обязательными полями
- При недоступности источника коннектор логирует ошибку и не падает весь pipeline
- Сырой JSON-ответ сохраняется в Raw Storage до парсинга
- Каждый запрос логирует: источник, маршрут, время, количество найденных рейсов

### 4.2 CDC Engine

**Описание:** Сравнивает текущий snapshot с предыдущим для одного маршрута/источника. Генерирует события `INSERT`, `UPDATE`, `DELETE`.

**Acceptance criteria:**
- `INSERT` — рейс появился в текущем snapshot, но отсутствовал в предыдущем
- `UPDATE` — рейс присутствует в обоих snapshot'ах, но изменилась цена или другие поля
- `DELETE` — рейс был в предыдущем snapshot, но исчез из текущего
- Все события записываются в таблицу `cdc_events` с временной меткой
- История изменений цены сохраняется в `flights_history` (SCD Type 2)
- `flights_current` всегда содержит актуальное состояние

### 4.3 Маршруты и маппинг источников

**Описание:** Маршруты хранятся как конфигурационные данные. Каждый источник может использовать отличающиеся коды аэропортов или городов — для этого предусмотрена таблица маппинга.

**Acceptance criteria:**
- Маршрут создаётся один раз и используется всеми коннекторами
- Для каждого источника существует маппинг: route_id + source → source-specific коды
- Если маппинг для источника отсутствует — коннектор для этого маршрута пропускается с логом
- Маршруты можно включать/отключать (поле `enabled`)

### 4.4 Уведомления

**Описание:** Telegram-бот отправляет уведомления при наступлении заданных условий.

**Acceptance criteria:**
- Уведомление отправляется, если цена опустилась ниже заданного порога (`max_price`)
- Уведомление отправляется при снижении цены более чем на N% относительно предыдущей
- Уведомление отправляется при достижении нового исторического минимума для маршрута
- Дублирующие уведомления за одну сессию не отправляются
- Сообщение содержит: маршрут, авиакомпанию, цену, дату вылета, ссылку на источник

### 4.5 Аналитика (Grafana)

**Описание:** Дашборд для наблюдения за динамикой цен.

**Acceptance criteria:**
- График изменения цены по времени для каждого маршрута
- Минимальная и средняя цена за период
- Лучшее текущее предложение по маршруту
- Активность источников (сколько рейсов собрано, ошибки)
- Количество CDC-событий по типам за период

---

## 5. Технический стек

| Компонент | Решение |
|---|---|
| Язык | Python 3.12+ |
| Browser automation | Playwright |
| HTTP-клиент | httpx |
| Парсинг JSON | orjson |
| Валидация моделей | Pydantic v2 |
| База данных | PostgreSQL |
| Оркестрация | Prefect |
| Контейнеризация | Docker Compose |
| Мониторинг | Prometheus + Grafana |
| Уведомления | Telegram Bot (python-telegram-bot) |
| Raw Storage | Локальная ФС (в будущем — S3/MinIO) |

---

## 6. Модель данных

### 6.1 Таблица `routes`

| Поле | Тип | Описание |
|---|---|---|
| route_id | SERIAL PK | Уникальный ID маршрута |
| origin | VARCHAR(10) | IATA-код аэропорта вылета |
| destination | VARCHAR(10) | IATA-код аэропорта прилёта |
| date_from | DATE | Начало диапазона дат поиска |
| date_to | DATE | Конец диапазона дат поиска |
| max_price | NUMERIC | Порог для уведомлений (опционально) |
| currency | VARCHAR(3) | Валюта (по умолчанию USD) |
| priority | INTEGER | Приоритет опроса (100 = высший) |
| search_interval | INTEGER | Минуты между опросами |
| enabled | BOOLEAN | Активен ли маршрут |
| notes | TEXT | Комментарий |

### 6.2 Таблица `source_route_mappings`

Хранит соответствие между внутренними кодами маршрута и кодами, которые используют конкретные источники.

| Поле | Тип | Описание |
|---|---|---|
| id | SERIAL PK | |
| route_id | INTEGER FK | Ссылка на routes |
| source | VARCHAR(50) | Имя источника (aviasales, trip, agoda) |
| source_origin | VARCHAR(50) | Код аэропорта/города в этом источнике |
| source_destination | VARCHAR(50) | Код аэропорта/города в этом источнике |
| enabled | BOOLEAN | Активен ли маппинг |

### 6.3 Модель `Flight` (унифицированная)

```
provider         : str       — источник (aviasales, trip, agoda)
airline          : str       — авиакомпания
flight_number    : str | None
origin           : str       — IATA-код
destination      : str       — IATA-код
departure_time   : datetime
arrival_time     : datetime
duration         : int       — минуты
stops            : int       — количество пересадок
price            : Decimal
currency         : str
scraped_at       : datetime
route_id         : int       — ссылка на routes
```

Никакой специфики конкретного источника внутри модели.

### 6.4 Таблица `flights_current`

Текущее состояние — одна запись на уникальный рейс (по ключу: provider + flight_number + departure_time + route_id).

### 6.5 Таблица `flights_history` (SCD Type 2)

Полная история изменений. Каждая запись содержит: `valid_from`, `valid_to`, `is_current`.

### 6.6 Таблица `cdc_events`

| Поле | Тип | Описание |
|---|---|---|
| id | SERIAL PK | |
| event_type | VARCHAR(10) | INSERT / UPDATE / DELETE |
| route_id | INTEGER FK | |
| source | VARCHAR(50) | |
| flight_key | VARCHAR(255) | Ключ рейса |
| old_price | NUMERIC | Для UPDATE/DELETE |
| new_price | NUMERIC | Для INSERT/UPDATE |
| changed_fields | JSONB | Все изменённые поля |
| occurred_at | TIMESTAMPTZ | |

### 6.7 Таблица `raw_snapshots`

Метаданные сохранённых JSON-файлов: путь, источник, маршрут, время, количество записей.

---

## 7. Data Layers

| Слой | Описание |
|---|---|
| **Raw** | Полный JSON-ответ источника. Не изменяется. Для повторного парсинга и отладки. |
| **Bronze** | Нормализованные поля конкретного источника — до унификации. |
| **Silver** | Единая модель `Flight`. Результат работы парсера. |
| **Gold** | Аналитические представления: min/avg цена, best offer, история маршрута. |

---

## 8. CDC Engine — детали

**Вход:**
- `previous_snapshot: list[Flight]` — результат предыдущего опроса
- `current_snapshot: list[Flight]` — результат текущего опроса

**Ключ сравнения:** `(provider, flight_number, departure_time, route_id)`

**Выход:**
- Список `CdcEvent` → записываются в `cdc_events`
- Обновление `flights_current`
- Добавление записей в `flights_history`

---

## 9. Высокоуровневая архитектура

```
Scheduler (Prefect)
        │
        ▼
Search Planner
(читает routes + source_route_mappings)
        │
        ▼
Source Connectors (параллельно)
    ├── Aviasales
    ├── Trip.com
    └── Agoda
        │
        ▼
Raw Storage (JSON files)
        │
        ▼
Parser → Silver (Flight objects)
        │
        ▼
CDC Engine
(сравнение с предыдущим snapshot)
        │
        ▼
PostgreSQL Warehouse
    ├── flights_current
    ├── flights_history
    └── cdc_events
        │
   ┌────┴─────────────┐
   ▼                  ▼
Grafana           Notifications
(аналитика)       (Telegram Bot)
```

---

## 10. UI / Дашборд

**v1 — Grafana:**
- Источник данных: PostgreSQL (прямые SQL-запросы)
- Дашборды: история цен, мин/средняя цена, лучшие предложения, активность источников
- Доступен только локально через Docker Compose

**v2 — Telegram Bot (будущее):**
- Просмотр текущих предложений по маршруту
- Добавление/удаление маршрутов
- Настройка порогов уведомлений
- Управление подпиской

---

## 11. Безопасность

- API-ключи и токены хранятся в `.env` файле, не в коде
- `.env` добавлен в `.gitignore`
- Playwright сессии не кэшируют авторизацию (stateless)
- Telegram Bot Token не логируется
- v1: нет публичного доступа, всё локально в Docker
- v2: при добавлении мультипользовательности — user_id изоляция данных

---

## 12. Нефункциональные требования

- Docker-first: весь стек поднимается командой `docker compose up`
- Каждый Connector независим и заменяем
- Минимум логики внутри Connector — только получение данных
- Бизнес-логика живёт в отдельных модулях (CDC, planner)
- Старые Raw JSON можно перепарсить без повторного запроса
- Легко добавить новый источник: создать файл коннектора + маппинги маршрутов

---

## 13. Этапы разработки

### Phase 1 — Infrastructure (критический путь)
- Docker Compose: PostgreSQL, Prefect, Grafana, Prometheus
- Миграции БД (все таблицы)
- Конфигурация маршрутов и маппингов
- Базовая модель `Flight` + валидация Pydantic

### Phase 2 — First Connector + Raw Storage
- Реализация Aviasales коннектора
- Raw Storage: сохранение JSON
- Парсер: JSON → Flight
- Ручной запуск и проверка

### Phase 3 — CDC Engine
- Сравнение snapshot'ов
- Генерация INSERT/UPDATE/DELETE событий
- Запись в `flights_current`, `flights_history`, `cdc_events`

### Phase 4 — Orchestration + Remaining Connectors
- Prefect flow для полного цикла
- Коннекторы Trip.com и Agoda
- Search Planner (читает routes, запускает коннекторы)

### Phase 5 — Analytics + Notifications
- Grafana дашборды
- Telegram Bot уведомления
- Метрики Prometheus

### Phase 6 — v2 (будущее)
- Мультипользовательский Telegram Bot
- UI для управления маршрутами
- Подписочная модель

---

## 14. Потенциальные проблемы и решения

| Проблема | Решение |
|---|---|
| Сайт меняет структуру XHR API | Raw Storage позволяет перепарсить старые данные без повторного запроса |
| Блокировка по IP/rate limiting | Настраиваемый `search_interval` на маршрут; случайные задержки между запросами |
| Playwright нестабилен | Изолировать в отдельный контейнер; retry-логика; fallback на httpx если возможно |
| Разные коды аэропортов у источников | `source_route_mappings` таблица решает проблему маппинга |
| Дублирование уведомлений | Дедупликация по `(route_id, event_type, flight_key)` в рамках временного окна |
| Рост объёма Raw Storage | Политика retention: удалять Raw JSON старше N дней (метаданные в БД остаются) |

---

## 15. Структура проекта

```
flight-monitor/
├── connectors/
│   ├── base.py          — абстрактный коннектор
│   ├── aviasales.py
│   ├── trip.py
│   └── agoda.py
├── planner/             — Search Planner, читает routes + mappings
├── parser/              — JSON → Flight
├── models/              — Pydantic модели (Flight, CdcEvent, Route)
├── cdc/                 — CDC Engine
├── warehouse/           — запись в PostgreSQL
├── storage/             — Raw Storage (файловая система)
├── scheduler/           — Prefect flows
├── notifications/       — Telegram Bot
├── dashboard/           — Grafana provisioning (datasources, dashboards)
├── migrations/          — SQL миграции
├── tests/
├── docs/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 16. Long-Term Vision

Проект должен выглядеть как реальная Data Platform, а не как учебный парсер.

Главная ценность — демонстрация полного цикла обработки данных:

```
Data Collection → Normalization → Storage → CDC → History → Analytics → Alerts
```

Итоговый результат: небольшой production-сервис мониторинга цен на авиабилеты с современной архитектурой Data Engineering, готовый к расширению до публичного Telegram-бота с подпиской.
