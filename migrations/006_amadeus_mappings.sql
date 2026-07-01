-- Add amadeus source_route_mappings for existing routes.
-- ON CONFLICT DO NOTHING is safe because (route_id, source) has a unique constraint.

INSERT INTO source_route_mappings (route_id, source, source_origin, source_destination, enabled)
SELECT r.route_id, v.source, v.source_origin, v.source_destination, true
FROM (VALUES
    ('HAN', 'KUL', 'amadeus', 'HAN', 'KUL'),
    ('KUL', 'CMB', 'amadeus', 'KUL', 'CMB'),
    ('CMB', 'MOW', 'amadeus', 'CMB', 'SVO')
) AS v(origin, destination, source, source_origin, source_destination)
JOIN routes r ON r.origin = v.origin AND r.destination = v.destination
ON CONFLICT (route_id, source) DO NOTHING;
