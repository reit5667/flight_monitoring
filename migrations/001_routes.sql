CREATE TABLE IF NOT EXISTS routes (
      route_id        SERIAL PRIMARY KEY,
      origin          VARCHAR(10)  NOT NULL,
      destination     VARCHAR(10)  NOT NULL,
      date_from       DATE         NOT NULL,
      date_to         DATE         NOT NULL,
      max_price       NUMERIC,
      currency        VARCHAR(3)   NOT NULL DEFAULT 'USD',
      priority        INTEGER      NOT NULL DEFAULT 50,
      search_interval INTEGER      NOT NULL DEFAULT 60,
      enabled         BOOLEAN      NOT NULL DEFAULT true,
      notes           TEXT
  );

  CREATE TABLE IF NOT EXISTS source_route_mappings (
      id                  SERIAL PRIMARY KEY,
      route_id            INTEGER      NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
      source              VARCHAR(50)  NOT NULL,
      source_origin       VARCHAR(50)  NOT NULL,
      source_destination  VARCHAR(50)  NOT NULL,
      enabled             BOOLEAN      NOT NULL DEFAULT true,
      UNIQUE (route_id, source)
  );