"""
IATA-коды аэропортов → русское название города.
Используется для отображения маршрутов в боте.
Также содержит обратный индекс для разбора текстового ввода (названия городов → IATA).
"""

# IATA → русское название города
AIRPORT_NAMES: dict[str, str] = {
    # Юго-Восточная Азия
    "HAN": "Ханой",
    "SGN": "Хошимин",
    "DAD": "Дананг",
    "BKK": "Бангкок",
    "DMK": "Бангкок (Дон Муанг)",
    "HKT": "Пхукет",
    "CNX": "Чиангмай",
    "USM": "Самуи",
    "KUL": "Куала-Лумпур",
    "PEN": "Пенанг",
    "SIN": "Сингапур",
    "CGK": "Джакарта",
    "DPS": "Бали (Денпасар)",
    "SUB": "Сурабая",
    "MNL": "Манила",
    "CEB": "Себу",
    "RGN": "Янгон",
    "REP": "Сиемреап",
    "PNH": "Пномпень",
    "VTE": "Вьентьян",
    "LPQ": "Луанг-Прабанг",
    # Южная Азия
    "CMB": "Коломбо",
    "DEL": "Дели",
    "BOM": "Мумбаи",
    "BLR": "Бангалор",
    "MAA": "Ченнай",
    "CCU": "Калькутта",
    "GOI": "Гоа",
    "KTM": "Катманду",
    "DAC": "Дакка",
    "MLE": "Мале",
    # Восточная Азия
    "PEK": "Пекин",
    "PKX": "Пекин (Дасин)",
    "PVG": "Шанхай",
    "SHA": "Шанхай (Хунцяо)",
    "CAN": "Гуанчжоу",
    "SZX": "Шэньчжэнь",
    "CTU": "Чэнду",
    "KMG": "Куньмин",
    "HKG": "Гонконг",
    "MFM": "Макао",
    "TPE": "Тайбэй",
    "ICN": "Сеул",
    "GMP": "Сеул (Кимпхо)",
    "NRT": "Токио (Нарита)",
    "HND": "Токио (Ханэда)",
    "KIX": "Осака",
    "CTS": "Саппоро",
    "OKA": "Окинава",
    # Средний Восток
    "DXB": "Дубай",
    "AUH": "Абу-Даби",
    "DOH": "Доха",
    "BAH": "Бахрейн",
    "KWI": "Кувейт",
    "MCT": "Маскат",
    "AMM": "Амман",
    "BEY": "Бейрут",
    "TLV": "Тель-Авив",
    "IST": "Стамбул",
    "SAW": "Стамбул (Сабиха)",
    "AYT": "Анталья",
    "GZP": "Аланья",
    # Центральная Азия
    "ALA": "Алматы",
    "NQZ": "Астана",
    "TAS": "Ташкент",
    "FRU": "Бишкек",
    "DYU": "Душанбе",
    "ASB": "Ашхабад",
    "GYD": "Баку",
    "EVN": "Ереван",
    "TBS": "Тбилиси",
    # Россия
    "MOW": "Москва",
    "SVO": "Москва (Шереметьево)",
    "DME": "Москва (Домодедово)",
    "VKO": "Москва (Внуково)",
    "LED": "Санкт-Петербург",
    "AER": "Сочи",
    "KZN": "Казань",
    "SVX": "Екатеринбург",
    "OVB": "Новосибирск",
    "KJA": "Красноярск",
    "IKT": "Иркутск",
    "UUS": "Южно-Сахалинск",
    "VVO": "Владивосток",
    # Европа
    "MIL": "Милан",  # meta-code, used when airport unspecified
    "MXP": "Милан (Мальпенса)",
    "LIN": "Милан (Линате)",
    "BGY": "Милан (Бергамо)",
    "FCO": "Рим",
    "NAP": "Неаполь",
    "VCE": "Венеция",
    "CDG": "Париж (Шарль-де-Голль)",
    "ORY": "Париж (Орли)",
    "LHR": "Лондон (Хитроу)",
    "LGW": "Лондон (Гатвик)",
    "STN": "Лондон (Станстед)",
    "AMS": "Амстердам",
    "FRA": "Франкфурт",
    "MUC": "Мюнхен",
    "BCN": "Барселона",
    "MAD": "Мадрид",
    "LIS": "Лиссабон",
    "ATH": "Афины",
    "WAW": "Варшава",
    "PRG": "Прага",
    "BEG": "Белград",
    "BUD": "Будапешт",
    "VIE": "Вена",
    "ZRH": "Цюрих",
    "CPH": "Копенгаген",
    "ARN": "Стокгольм",
    "HEL": "Хельсинки",
    "OSL": "Осло",
    # Северная Америка
    "JFK": "Нью-Йорк (JFK)",
    "EWR": "Нью-Йорк (Ньюарк)",
    "LAX": "Лос-Анджелес",
    "SFO": "Сан-Франциско",
    "ORD": "Чикаго",
    "MIA": "Майами",
    "YYZ": "Торонто",
    "MEX": "Мехико",
    "CUN": "Канкун",
    # Прочее
    "SYD": "Сидней",
    "MEL": "Мельбурн",
    "CAI": "Каир",
    "JNB": "Йоханнесбург",
    "NBO": "Найроби",
}

# Обратный индекс: нижний регистр → IATA (для разбора текстового ввода)
# Включает русские и английские варианты написания
_CITY_ALIASES: dict[str, str] = {
    # Русские названия (нижний регистр)
    "ханой": "HAN",
    "хошимин": "SGN",
    "сайгон": "SGN",
    "дананг": "DAD",
    "бангкок": "BKK",
    "пхукет": "HKT",
    "чиангмай": "CNX",
    "самуи": "USM",
    "куала-лумпур": "KUL",
    "куалалумпур": "KUL",
    "кл": "KUL",
    "пенанг": "PEN",
    "сингапур": "SIN",
    "джакарта": "CGK",
    "бали": "DPS",
    "денпасар": "DPS",
    "манила": "MNL",
    "себу": "CEB",
    "янгон": "RGN",
    "рангун": "RGN",
    "сиемреап": "REP",
    "пномпень": "PNH",
    "вьентьян": "VTE",
    "луанг-прабанг": "LPQ",
    "коломбо": "CMB",
    "дели": "DEL",
    "мумбаи": "BOM",
    "бомбей": "BOM",
    "бангалор": "BLR",
    "ченнай": "MAA",
    "мадрас": "MAA",
    "калькутта": "CCU",
    "гоа": "GOI",
    "катманду": "KTM",
    "мале": "MLE",
    "пекин": "PEK",
    "шанхай": "PVG",
    "гуанчжоу": "CAN",
    "шэньчжэнь": "SZX",
    "чэнду": "CTU",
    "куньмин": "KMG",
    "гонконг": "HKG",
    "макао": "MFM",
    "тайбэй": "TPE",
    "сеул": "ICN",
    "токио": "NRT",
    "осака": "KIX",
    "дубай": "DXB",
    "абу-даби": "AUH",
    "абудаби": "AUH",
    "доха": "DOH",
    "стамбул": "IST",
    "анталья": "AYT",
    "алматы": "ALA",
    "астана": "NQZ",
    "ташкент": "TAS",
    "бишкек": "FRU",
    "баку": "GYD",
    "ереван": "EVN",
    "тбилиси": "TBS",
    "москва": "MOW",
    "мск": "MOW",
    "шереметьево": "SVO",
    "домодедово": "DME",
    "внуково": "VKO",
    "питер": "LED",
    "санкт-петербург": "LED",
    "спб": "LED",
    "сочи": "AER",
    "казань": "KZN",
    "екатеринбург": "SVX",
    "новосибирск": "OVB",
    "иркутск": "IKT",
    "владивосток": "VVO",
    "милан": "MIL",
    "рим": "FCO",
    "неаполь": "NAP",
    "венеция": "VCE",
    "париж": "CDG",
    "лондон": "LHR",
    "амстердам": "AMS",
    "франкфурт": "FRA",
    "мюнхен": "MUC",
    "барселона": "BCN",
    "мадрид": "MAD",
    "лиссабон": "LIS",
    "афины": "ATH",
    "варшава": "WAW",
    "прага": "PRG",
    "белград": "BEG",
    "будапешт": "BUD",
    "вена": "VIE",
    "цюрих": "ZRH",
    "копенгаген": "CPH",
    "стокгольм": "ARN",
    "хельсинки": "HEL",
    "осло": "OSL",
    "нью-йорк": "JFK",
    "нью йорк": "JFK",
    "лос-анджелес": "LAX",
    "лосанджелес": "LAX",
    "сан-франциско": "SFO",
    "чикаго": "ORD",
    "майами": "MIA",
    "торонто": "YYZ",
    "мехико": "MEX",
    "канкун": "CUN",
    "сидней": "SYD",
    "мельбурн": "MEL",
    "каир": "CAI",
    # Английские названия (нижний регистр)
    "hanoi": "HAN",
    "ho chi minh": "SGN",
    "saigon": "SGN",
    "hcmc": "SGN",
    "da nang": "DAD",
    "danang": "DAD",
    "bangkok": "BKK",
    "phuket": "HKT",
    "chiang mai": "CNX",
    "chiangmai": "CNX",
    "samui": "USM",
    "kuala lumpur": "KUL",
    "penang": "PEN",
    "singapore": "SIN",
    "jakarta": "CGK",
    "bali": "DPS",
    "denpasar": "DPS",
    "manila": "MNL",
    "cebu": "CEB",
    "yangon": "RGN",
    "rangoon": "RGN",
    "siem reap": "REP",
    "phnom penh": "PNH",
    "vientiane": "VTE",
    "luang prabang": "LPQ",
    "colombo": "CMB",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "chennai": "MAA",
    "madras": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "goa": "GOI",
    "kathmandu": "KTM",
    "male": "MLE",
    "beijing": "PEK",
    "peking": "PEK",
    "shanghai": "PVG",
    "guangzhou": "CAN",
    "canton": "CAN",
    "shenzhen": "SZX",
    "chengdu": "CTU",
    "kunming": "KMG",
    "hong kong": "HKG",
    "hongkong": "HKG",
    "macau": "MFM",
    "macao": "MFM",
    "taipei": "TPE",
    "seoul": "ICN",
    "tokyo": "NRT",
    "osaka": "KIX",
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "doha": "DOH",
    "istanbul": "IST",
    "antalya": "AYT",
    "almaty": "ALA",
    "astana": "NQZ",
    "nur-sultan": "NQZ",
    "tashkent": "TAS",
    "bishkek": "FRU",
    "baku": "GYD",
    "yerevan": "EVN",
    "tbilisi": "TBS",
    "moscow": "MOW",
    "saint petersburg": "LED",
    "st petersburg": "LED",
    "sochi": "AER",
    "milan": "MIL",
    "rome": "FCO",
    "naples": "NAP",
    "venice": "VCE",
    "paris": "CDG",
    "london": "LHR",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "munich": "MUC",
    "barcelona": "BCN",
    "madrid": "MAD",
    "lisbon": "LIS",
    "athens": "ATH",
    "warsaw": "WAW",
    "prague": "PRG",
    "belgrade": "BEG",
    "beograd": "BEG",
    "budapest": "BUD",
    "vienna": "VIE",
    "zurich": "ZRH",
    "copenhagen": "CPH",
    "stockholm": "ARN",
    "helsinki": "HEL",
    "oslo": "OSL",
    "new york": "JFK",
    "newyork": "JFK",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "ORD",
    "miami": "MIA",
    "toronto": "YYZ",
    "mexico city": "MEX",
    "cancun": "CUN",
    "sydney": "SYD",
    "melbourne": "MEL",
    "cairo": "CAI",
}


def iata_to_city(code: str) -> str:
    """Вернуть русское название города по IATA-коду, или сам код если не найден."""
    return AIRPORT_NAMES.get(code.upper(), code.upper())


def route_label(origin: str, dest: str) -> str:
    """Построить читаемый лейбл маршрута из IATA-кодов."""
    return f"{iata_to_city(origin)} → {iata_to_city(dest)}"


def resolve_city(text: str) -> str | None:
    """
    Попробовать распознать текст как IATA-код или название города.
    Возвращает IATA-код в верхнем регистре или None если не распознан.
    """
    text = text.strip()
    upper = text.upper()

    # Уже IATA-код
    if len(upper) == 3 and upper.isalpha():
        return upper

    # Поиск по алиасам (нижний регистр)
    lower = text.lower()
    if lower in _CITY_ALIASES:
        return _CITY_ALIASES[lower]

    # Частичное совпадение: ищем алиас который начинается с введённого текста
    matches = [iata for alias, iata in _CITY_ALIASES.items() if alias.startswith(lower) and len(lower) >= 3]
    if len(matches) == 1:
        return matches[0]

    return None


def parse_route_input(text: str) -> tuple[str, str] | None:
    """
    Разобрать строку ввода маршрута.
    Принимает: 'HAN BKK', 'Ханой Бангкок', 'hanoi bangkok', 'HAN Bangkok' и т.д.
    Возвращает (origin, dest) в верхнем регистре или None если не удалось распознать.
    """
    parts = text.strip().split()
    if len(parts) == 2:
        origin = resolve_city(parts[0])
        dest = resolve_city(parts[1])
        if origin and dest:
            return origin, dest

    # Попробовать разбить по стрелке или дефису
    for sep in ("→", "->", "-", ","):
        if sep in text:
            halves = text.split(sep, 1)
            origin = resolve_city(halves[0].strip())
            dest = resolve_city(halves[1].strip())
            if origin and dest:
                return origin, dest

    return None


def search_cities(query: str, limit: int = 5) -> list[tuple[str, str]]:
    """
    Найти города по частичному вводу (≥2 символа).
    Возвращает список (iata, русское_название), уникальных, отсортированных по названию.
    """
    q = query.strip().lower()
    if len(q) < 2:
        return []

    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for alias, iata in _CITY_ALIASES.items():
        if alias.startswith(q) and iata not in seen:
            seen.add(iata)
            results.append((iata, AIRPORT_NAMES.get(iata, iata)))

    results.sort(key=lambda x: x[1])
    return results[:limit]
