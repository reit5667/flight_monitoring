-- Seed MVP маршрутов.
-- Используем WHERE NOT EXISTS вместо ON CONFLICT DO NOTHING, потому что
-- у routes нет уникального ключа на (origin, destination) — только route_id (PK).
-- ON CONFLICT DO NOTHING без подходящего constraint был бы no-op и не защищал от дублей.

INSERT INTO routes (origin, destination, date_from, date_to, max_price, currency, priority, search_interval, enabled, notes)
SELECT * FROM (VALUES
    ('HAN', 'KUL', '2026-07-01'::date, '2026-12-31'::date, 200.00::numeric, 'USD', 90, 60,  true, 'Ханой → Куала-Лумпур'),
    ('KUL', 'CMB', '2026-07-01'::date, '2026-12-31'::date, 150.00::numeric, 'USD', 70, 90,  true, 'Куала-Лумпур → Коломбо'),
    ('CMB', 'MOW', '2026-07-01'::date, '2026-12-31'::date, 500.00::numeric, 'USD', 80, 120, true, 'Коломбо → Москва')
) AS v(origin, destination, date_from, date_to, max_price, currency, priority, search_interval, enabled, notes)
WHERE NOT EXISTS (
    SELECT 1 FROM routes r WHERE r.origin = v.origin AND r.destination = v.destination
);

INSERT INTO source_route_mappings (route_id, source, source_origin, source_destination, enabled)
SELECT r.route_id, v.source, v.source_origin, v.source_destination, true
FROM (VALUES
    ('HAN', 'KUL', 'aviasales', 'HAN', 'KUL'),
    ('HAN', 'KUL', 'trip',      'HAN', 'KUL'),
    ('HAN', 'KUL', 'agoda',     'HAN', 'KUL'),
    ('KUL', 'CMB', 'aviasales', 'KUL', 'CMB'),
    ('KUL', 'CMB', 'trip',      'KUL', 'CMB'),
    ('KUL', 'CMB', 'agoda',     'KUL', 'CMB'),
    ('CMB', 'MOW', 'aviasales', 'CMB', 'SVO'),
    ('CMB', 'MOW', 'trip',      'CMB', 'MOW'),
    ('CMB', 'MOW', 'agoda',     'CMB', 'MOW')
) AS v(origin, destination, source, source_origin, source_destination)
JOIN routes r ON r.origin = v.origin AND r.destination = v.destination
ON CONFLICT (route_id, source) DO NOTHING;
