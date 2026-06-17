-- Текущий снимок цен: одна строка на рейс, всегда актуальная цена.
-- Когда цена меняется — мы делаем UPDATE этой строки (не INSERT новой).
CREATE TABLE IF NOT EXISTS flights_current (
    id               BIGSERIAL PRIMARY KEY,
    route_id         INTEGER       NOT NULL REFERENCES routes(route_id) ON DELETE RESTRICT,
    provider         VARCHAR(50)   NOT NULL,
    airline          VARCHAR(100)  NOT NULL,
    flight_number    VARCHAR(20),
    origin           CHAR(3)       NOT NULL,
    destination      CHAR(3)       NOT NULL,
    departure_time   TIMESTAMPTZ   NOT NULL,
    arrival_time     TIMESTAMPTZ   NOT NULL,
    duration_minutes INTEGER       NOT NULL,
    stops            INTEGER       NOT NULL DEFAULT 0,
    price            NUMERIC(10,2) NOT NULL CHECK (price > 0),
    currency         CHAR(3)       NOT NULL DEFAULT 'USD',
    scraped_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    -- Уникальный ключ: один и тот же рейс не может появиться дважды.
    -- flight_number может быть NULL (чартеры), поэтому используем NULLS NOT DISTINCT
    -- чтобы два NULL не считались разными значениями.
    UNIQUE NULLS NOT DISTINCT (provider, flight_number, departure_time, route_id)
);

-- История изменений: SCD Type 2.
-- Каждый раз когда цена меняется — старая строка "закрывается" (valid_to = now, is_current = false),
-- и добавляется новая (valid_from = now, valid_to = NULL, is_current = true).
-- Строки НИКОГДА не удаляются — только добавляются. Это позволяет воспроизвести
-- состояние цен на любой момент времени в прошлом.
CREATE TABLE IF NOT EXISTS flights_history (
    id               BIGSERIAL PRIMARY KEY,
    route_id         INTEGER       NOT NULL REFERENCES routes(route_id) ON DELETE RESTRICT,
    provider         VARCHAR(50)   NOT NULL,
    airline          VARCHAR(100)  NOT NULL,
    flight_number    VARCHAR(20),
    origin           CHAR(3)       NOT NULL,
    destination      CHAR(3)       NOT NULL,
    departure_time   TIMESTAMPTZ   NOT NULL,
    arrival_time     TIMESTAMPTZ   NOT NULL,
    duration_minutes INTEGER       NOT NULL,
    stops            INTEGER       NOT NULL DEFAULT 0,
    price            NUMERIC(10,2) NOT NULL CHECK (price > 0),
    currency         CHAR(3)       NOT NULL DEFAULT 'USD',
    scraped_at       TIMESTAMPTZ   NOT NULL,
    -- SCD Type 2 поля:
    valid_from       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    valid_to         TIMESTAMPTZ,               -- NULL означает "эта запись сейчас актуальна"
    is_current       BOOLEAN       NOT NULL DEFAULT true
);

-- Индекс для быстрого поиска актуальной записи по рейсу
CREATE INDEX IF NOT EXISTS idx_flights_history_current
    ON flights_history (provider, flight_number, departure_time, route_id)
    WHERE is_current = true;

-- Журнал CDC событий: каждое изменение фиксируется здесь.
-- changed_fields — JSONB вида {"price": {"old": 150.00, "new": 130.00}}.
-- Эта таблица растёт только вперёд — никаких UPDATE или DELETE.
CREATE TABLE IF NOT EXISTS cdc_events (
    id             BIGSERIAL PRIMARY KEY,
    route_id       INTEGER      NOT NULL REFERENCES routes(route_id) ON DELETE RESTRICT,
    source         VARCHAR(50)  NOT NULL,
    flight_key     TEXT         NOT NULL,  -- 'provider:flight_number:departure_time'
    -- CHECK constraint гарантирует на уровне БД, что event_type может быть
    -- только одним из трёх значений. Python-код тоже проверяет, но БД — последний рубеж.
    event_type     VARCHAR(10)  NOT NULL CHECK (event_type IN ('INSERT', 'UPDATE', 'DELETE')),
    old_price      NUMERIC(10,2),
    new_price      NUMERIC(10,2),
    changed_fields JSONB        NOT NULL DEFAULT '{}',
    occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Индекс для аналитики: часто будем смотреть события по маршруту и времени
CREATE INDEX IF NOT EXISTS idx_cdc_events_route_time
    ON cdc_events (route_id, occurred_at DESC);

-- Метаданные о сырых файлах. Сами файлы лежат на диске (raw_storage/),
-- здесь только путь к файлу и счётчики. Нужно для:
-- 1) аудита — сколько рейсов нашли за каждый запрос
-- 2) перепарсинга — можно взять file_path и перечитать файл с новым парсером
CREATE TABLE IF NOT EXISTS raw_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    route_id       INTEGER      NOT NULL REFERENCES routes(route_id) ON DELETE RESTRICT,
    source         VARCHAR(50)  NOT NULL,
    file_path      TEXT         NOT NULL,
    records_count  INTEGER      NOT NULL DEFAULT 0,
    scraped_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
