-- Подписки пользователей на маршруты для алёртов в Telegram-боте
CREATE TABLE IF NOT EXISTS subscriptions (
    id           BIGSERIAL PRIMARY KEY,
    chat_id      BIGINT       NOT NULL,
    route_id     INTEGER      NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    origin       VARCHAR(3)   NOT NULL,
    dest         VARCHAR(3)   NOT NULL,
    alert_price  NUMERIC(10,2) NOT NULL,  -- цена на момент подписки
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_route_active
    ON subscriptions (route_id, is_active);
