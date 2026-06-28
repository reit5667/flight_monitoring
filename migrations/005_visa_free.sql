ALTER TABLE routes ADD COLUMN IF NOT EXISTS visa_free BOOLEAN NOT NULL DEFAULT true;

-- Шенгенские маршруты помечаем как visa_free = false
UPDATE routes SET visa_free = false WHERE destination IN (
    -- Шенген: Австрия, Бельгия, Чехия, Дания, Эстония, Финляндия, Франция,
    -- Германия, Греция, Венгрия, Исландия, Италия, Латвия, Лихтенштейн, Литва,
    -- Люксембург, Мальта, Нидерланды, Норвегия, Польша, Португалия, Словакия,
    -- Словения, Испания, Швеция, Швейцария
    'VIE', 'GRZ', 'LNZ', 'SZG',               -- Австрия
    'BRU', 'CRL', 'LGG',                        -- Бельгия
    'PRG', 'BRQ', 'OSR',                        -- Чехия
    'CPH', 'AAL', 'AAR',                        -- Дания
    'TLL',                                       -- Эстония
    'HEL', 'TMP', 'TKU', 'OUL',               -- Финляндия
    'CDG', 'ORY', 'NCE', 'LYS', 'MRS', 'BOD', 'TLS', 'NTE', 'SXB', -- Франция
    'FRA', 'MUC', 'BER', 'HAM', 'DUS', 'STR', 'CGN', 'NUE', 'LEJ', 'HAJ', -- Германия
    'ATH', 'SKG', 'HER', 'RHO', 'CFU', 'KGS', 'ZTH', 'CHQ', 'JSI', -- Греция
    'BUD', 'DEB',                               -- Венгрия
    'KEF',                                       -- Исландия
    'FCO', 'MIL', 'MXP', 'LIN', 'BGY', 'VCE', 'NAP', 'BLQ', 'CTA', 'PSA', 'PMO', 'BRI', 'CAG', -- Италия
    'RIX',                                       -- Латвия
    'VNO', 'KUN',                               -- Литва
    'LUX',                                       -- Люксембург
    'MLA',                                       -- Мальта
    'AMS', 'EIN', 'RTM',                        -- Нидерланды
    'OSL', 'BGO', 'TRD', 'SVG',               -- Норвегия
    'WAW', 'KRK', 'KTW', 'GDN', 'POZ', 'WRO', -- Польша
    'LIS', 'OPO', 'FAO',                        -- Португалия
    'BTS', 'KSC',                               -- Словакия
    'LJU',                                       -- Словения
    'MAD', 'BCN', 'AGP', 'PMI', 'ALC', 'VLC', 'IBZ', 'SVQ', 'BIO', 'TFS', 'LPA', -- Испания
    'ARN', 'GOT', 'MMX',                        -- Швеция
    'ZRH', 'GVA', 'BSL'                         -- Швейцария
);
