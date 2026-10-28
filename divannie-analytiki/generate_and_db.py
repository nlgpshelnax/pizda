import json
import random
import re
from datetime import date, timedelta
from collections import Counter

random.seed(42)

# ===============================================================
# ОБЩИЙ СПРАВОЧНИК КОДОВ (синхронизирован с cities.py)
# ===============================================================
CITY_CODES = {
    "Москва": "MOW", "Санкт-Петербург": "LED", "Казань": "KZN", "Екатеринбург": "SVX",
    "Сочи": "AER", "Париж": "CDG", "Рим": "FCO", "Ницца": "NCE", "Барселона": "BCN",
    "Инсбрук": "INN", "Церматт": "ZRH", "Вена": "VIE", "Прага": "PRG", "Мюнхен": "MUC",
    "Милан": "MIL", "Осло": "OSL", "Флоренция": "FLR", "Мадрид": "MAD", "Берлин": "BER",
    "Лондон": "LON", "Анси": "ANC", "Больцано": "BOL", "Интерлакен": "INT",
    "Уиндермир": "WND", "Сан-Марино": "SMA", "Виши": "VHY", "Монтекатини-Терме": "MTC",
    "Баден-Баден": "BAD", "Бад-Гастайн": "BGS", "Бад-Рагац": "BRG", "Карловы Вары": "KLV",
    "Будапешт": "BUD", "Сьерра-Невада": "GRX", "Шамони-Монблан": "CMF",
    "Кортина-д’Ампеццо": "CORT", "Гармиш-Партенкирхен": "GPI", "Андорра-ла-Велья": "AND",
    "Палермо": "PMO", "Малага": "AGP", "Ханья": "CHQ", "Фару": "FAO", "Монте-Карло": "MCM",
    "Белград": "BEG", "Копаоник": "KOP", "Врнячка-Баня": "VRN", "Будва": "TIV",
    "Жабляк": "ZBL", "Сараево": "SJJ", "Яхорина": "JAH",
}

def city_code(name: str) -> str:
    return CITY_CODES[name]

def fmt(mins: int) -> str:
    mins %= 24 * 60
    return f"{mins // 60:02d}:{mins % 60:02d}"

def to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m

# ===============================================================
# ЧАСТЬ 1: ГЕНЕРАЦИЯ ОТЕЛЕЙ
# ===============================================================
def generate_hotels(
    target_total: int = 1000,
    pets_ratio: float = 0.40,
    out_path: str = "hotels.json",
) -> list:
    HOTEL_CITIES = [
        ("Шамони-Монблан", "Франция", "ski", (9000, 26000)),
        ("Кортина-д’Ампеццо", "Италия", "ski", (9000, 26000)),
        ("Инсбрук", "Австрия", "ski", (9000, 26000)),
        ("Церматт", "Швейцария", "ski", (9000, 26000)),
        ("Сьерра-Невада", "Испания", "ski", (9000, 26000)),
        ("Гармиш-Партенкирхен", "Германия", "ski", (9000, 26000)),
        ("Копаоник", "Сербия", "ski", (9000, 26000)),
        ("Жабляк", "Черногория", "ski", (9000, 26000)),
        ("Яхорина", "Босния", "ski", (9000, 26000)),
        ("Андорра-ла-Велья", "Андорра", "ski", (9000, 26000)),
        ("Ницца", "Франция", "beach", (6500, 22000)),
        ("Палермо", "Италия", "beach", (6500, 22000)),
        ("Барселона", "Испания", "beach", (6500, 22000)),
        ("Малага", "Испания", "beach", (6500, 22000)),
        ("Ханья", "Греция", "beach", (6500, 22000)),
        ("Будва", "Черногория", "beach", (6500, 22000)),
        ("Фару", "Португалия", "beach", (6500, 22000)),
        ("Монте-Карло", "Монако", "beach", (6500, 22000)),
        ("Сочи", "Россия", "beach", (6500, 22000)),
        ("Париж", "Франция", "culture", (5500, 18000)),
        ("Рим", "Италия", "culture", (5500, 18000)),
        ("Флоренция", "Италия", "culture", (5500, 18000)),
        ("Мадрид", "Испания", "culture", (5500, 18000)),
        ("Берлин", "Германия", "culture", (5500, 18000)),
        ("Лондон", "Великобритания", "culture", (5500, 18000)),
        ("Вена", "Австрия", "culture", (5500, 18000)),
        ("Прага", "Чехия", "culture", (5500, 18000)),
        ("Белград", "Сербия", "culture", (5500, 18000)),
        ("Сараево", "Босния", "culture", (5500, 18000)),
        ("Казань", "Россия", "culture", (5500, 18000)),
        ("Милан", "Италия", "culture", (5500, 18000)),
        ("Виши", "Франция", "spa", (5000, 24000)),
        ("Монтекатини-Терме", "Италия", "spa", (5000, 24000)),
        ("Баден-Баден", "Германия", "spa", (5000, 24000)),
        ("Бад-Гастайн", "Австрия", "spa", (5000, 24000)),
        ("Бад-Рагац", "Швейцария", "spa", (5000, 24000)),
        ("Карловы Вары", "Чехия", "spa", (5000, 24000)),
        ("Будапешт", "Венгрия", "spa", (5000, 24000)),
        ("Врнячка-Баня", "Сербия", "spa", (5000, 24000)),
        ("Анси", "Франция", "nature", (8000, 21000)),
        ("Больцано", "Италия", "nature", (8000, 21000)),
        ("Интерлакен", "Швейцария", "nature", (8000, 21000)),
        ("Уиндермир", "Великобритания", "nature", (8000, 21000)),
        ("Осло", "Норвегия", "nature", (8000, 21000)),
        ("Сан-Марино", "Сан-Марино", "nature", (8000, 21000)),
        ("Мюнхен", "Германия", "nature", (8000, 21000)),
    ]

    BRAND_TEMPLATES = {
        "Ibis":              ("Ibis {city}", 3),
        "Ibis Styles":       ("Ibis Styles {city}", 3),
        "Ibis Budget":       ("Ibis Budget {city}", 3),
        "Novotel":           ("Novotel {city}", 4),
        "Mercure":           ("Mercure {city}", 4),
        "Radisson Blu":      ("Radisson Blu Hotel {city}", 5),
        "Radisson":          ("Radisson Hotel {city}", 4),
        "Park Inn":          ("Park Inn by Radisson {city}", 4),
        "Hilton":            ("Hilton {city}", 5),
        "DoubleTree":        ("DoubleTree by Hilton {city}", 4),
        "Hampton":           ("Hampton by Hilton {city}", 3),
        "Marriott":          ("Marriott {city}", 5),
        "Courtyard":         ("Courtyard by Marriott {city}", 4),
        "B&B Hotels":        ("B&B Hotel {city}", 3),
        "NH Hotels":         ("NH {city}", 4),
        "Meliá":             ("Meliá {city}", 5),
        "Iberostar":         ("Iberostar {city}", 5),
        "Austria Trend":     ("Austria Trend Hotel {city}", 4),
        "Best Western":      ("Best Western {city}", 3),
        "Holiday Inn":       ("Holiday Inn {city}", 4),
        "Crowne Plaza":      ("Crowne Plaza {city}", 5),
        "Leonardo":          ("Leonardo Hotel {city}", 4),
        "Motel One":         ("Motel One {city}", 3),
        "MEININGER":         ("MEININGER Hotel {city}", 3),
        "Aparthotel Adagio": ("Aparthotel Adagio {city}", 4),
    }

    BOUTIQUE = {
        "Париж": [("Hôtel de Crillon", 5), ("Le Meurice", 5), ("Hôtel Lutetia", 5),
                  ("Hôtel du Louvre", 5), ("Le Grand Véfour", 4)],
        "Рим": [("Hotel Quirinale Roma", 4), ("Hotel Artemide Roma", 4),
                ("Hotel de Russie Roma", 5), ("Hotel Nazionale Roma", 4)],
        "Флоренция": [("Hotel Savoy Florence", 5), ("FH55 Hotel Calzaiuoli", 4),
                      ("Hotel degli Orafi Firenze", 4), ("Palazzo Vecchietti", 5)],
        "Мадрид": [("Hotel Ritz Madrid", 5), ("Hotel Palace Madrid", 5),
                   ("Hotel Vincci Soho", 4), ("Petit Palace Posada del Peine", 3)],
        "Берлин": [("Hotel Adlon Kempinski Berlin", 5), ("Hotel de Rome Berlin", 5),
                   ("Hotel Concorde Berlin", 5), ("Hotel Zoo Berlin", 4)],
        "Лондон": [("The Ritz London", 5), ("The Savoy London", 5),
                   ("The Langham London", 5), ("Claridge's London", 5)],
        "Вена": [("Hotel Sacher Wien", 5), ("Hotel Imperial Wien", 5),
                 ("Grand Hotel Wien", 5), ("Hotel Bristol Wien", 5)],
        "Прага": [("Hotel Paris Prague", 5), ("Hotel Josef Prague", 4),
                  ("Hotel Aria Prague", 5), ("Hotel Pod Věží Prague", 4)],
        "Белград": [("Hotel Moskva", 4), ("Metropol Palace Belgrade", 5),
                    ("Hotel Majestic Belgrade", 4)],
        "Сараево": [("Hotel Europe Sarajevo", 5), ("Hotel Central Sarajevo", 4),
                    ("Hotel Astra Sarajevo", 3)],
        "Казань": [("Мираж Казань", 5), ("Courtyard Kazan Kremlin", 4),
                   ("Гранд Отель Казань", 4), ("Ногай Казань", 3)],
        "Сочи": [("Radisson Blu Resort Sochi", 5), ("Родина Гранд Отель Сочи", 5),
                 ("Pullman Sochi Centre", 5)],
        "Ницца": [("Hôtel Negresco Nice", 5), ("Hôtel Le Grimaldi Nice", 4),
                  ("Hôtel Beau Rivage Nice", 4)],
        "Барселона": [("Hotel Arts Barcelona", 5), ("Hotel Majestic Barcelona", 5),
                      ("Hotel Casa Fuster Barcelona", 5)],
        "Монте-Карло": [("Hôtel de Paris Monte-Carlo", 5),
                        ("Hôtel Hermitage Monte-Carlo", 5),
                        ("Hotel Metropole Monte-Carlo", 4)],
        "Будапешт": [("Gellért Hotel Budapest", 5), ("Danubius Hotel Astoria Budapest", 4),
                     ("Hotel Corinthia Budapest", 5)],
        "Карловы Вары": [("Grandhotel Pupp Karlovy Vary", 5),
                         ("Hotel Thermal Karlovy Vary", 4)],
        "Баден-Баден": [("Brenners Park-Hotel Baden-Baden", 5),
                        ("Hotel Merkur Baden-Baden", 4)],
        "Бад-Гастайн": [("Hotel Sacher Bad Gastein", 5),
                        ("Hotel Salzburger Hof Bad Gastein", 4)],
        "Бад-Рагац": [("Grand Resort Bad Ragaz", 5), ("Hotel Hof Ragaz", 4)],
        "Сан-Марино": [("Grand Hotel San Marino", 5), ("Hotel Titano San Marino", 3)],
        "Интерлакен": [("Victoria Jungfrau Interlaken", 5), ("Metropole Interlaken", 4)],
        "Церматт": [("Grand Hotel Zermatterhof", 5), ("Mont Cervin Palace Zermatt", 4)],
        "Осло": [("Grand Hotel Oslo", 5), ("Radisson Blu Scandinavia Oslo", 4)],
        "Уиндермир": [("The Belsfield Windermere", 5),
                      ("Macdonald Old England Hotel Windermere", 4)],
        "Анси": [("Impérial Palace Annecy", 5), ("Hôtel du Palais de l'Isle Annecy", 4)],
        "Больцано": [("Parkhotel Laurin Bolzano", 5), ("Hotel Greif Bolzano", 4)],
        "Кортина-д’Ампеццо": [("Hotel Cristallo Cortina", 5),
                              ("Hotel de la Poste Cortina", 4)],
        "Инсбрук": [("Hotel Goldener Adler Innsbruck", 5)],
        "Гармиш-Партенкирхен": [("Hotel Zugspitze Garmisch", 5)],
        "Копаоник": [("Grand Hotel Kopaonik", 5), ("Viceroy Kopaonik", 4)],
        "Жабляк": [("Hotel Soa Zabljak", 5), ("Hotel Polar Star Zabljak", 4)],
        "Яхорина": [("Hotel Termag Jahorina", 5), ("Hotel Rajska Dolina Jahorina", 4)],
        "Андорра-ла-Велья": [("Andorra Park Hotel", 5), ("Hotel Roc Blanc Andorra", 4)],
        "Палермо": [("Grand Hotel Villa Igiea Palermo", 5), ("Hotel Politeama Palermo", 4)],
        "Малага": [("Gran Hotel Miramar Malaga", 5), ("Hotel Molina Lario Malaga", 4)],
        "Ханья": [("Domes Noruz Chania", 5), ("Kydon The Heart City Hotel Chania", 4)],
        "Будва": [("Hotel Splendid Budva", 5), ("Hotel Slavija Budva", 4)],
        "Фару": [("Hotel Faro & Beach Club", 5), ("Eva Senses Hotel Faro", 4)],
        "Виши": [("Vichy Célestins Spa Hôtel", 5), ("Hôtel Aletti Palace Vichy", 4)],
        "Монтекатини-Терме": [("Grand Hotel Terme Montecatini", 5),
                              ("Hotel Ercolini & Savi Montecatini", 4)],
        "Врнячка-Баня": [("Hotel Zepter Vrnjacka Banja", 5),
                         ("Hotel Breza Vrnjacka Banja", 4)],
        "Сьерра-Невада": [("Melia Sierra Nevada", 5), ("Vincci Selección Rumaykiyya", 4)],
        "Шамони-Монблан": [("Hôtel Mont-Blanc Chamonix", 5), ("Le Morgane Chamonix", 4)],
        "Милан": [("Hotel Principe di Savoia Milano", 5), ("Hotel Galleria Milano", 4),
                  ("NH Milano Duomo", 4)],
        "Мюнхен": [("Hotel Bayerischer Hof München", 5),
                   ("Hotel Vier Jahreszeiten Kempinski München", 5),
                   ("Motel One München City", 3), ("Hotel Deutsche Eiche München", 3)],
    }

    hotels = []
    used_names_per_city = {}
    counter_per_code = {}

    def next_id(code: str) -> str:
        n = counter_per_code.get(code, 0) + 1
        counter_per_code[code] = n
        return f"h_{code.lower()}_{n:03d}"

    def register_name(city: str, name: str) -> bool:
        used = used_names_per_city.setdefault(city, set())
        if name in used:
            return False
        used.add(name)
        return True

    def make_price(pmin: int, pmax: int, stars: int) -> int:
        if stars == 5:
            lo, hi = pmin + int((pmax - pmin) * 0.55), pmax
        elif stars == 4:
            lo, hi = pmin + int((pmax - pmin) * 0.30), pmin + int((pmax - pmin) * 0.75)
        else:
            lo, hi = pmin, pmin + int((pmax - pmin) * 0.45)
        return int(round(random.randint(lo, hi) / 100.0)) * 100

    for city, country, vibe, prange in HOTEL_CITIES:
        code = city_code(city)
        for name, stars in BOUTIQUE.get(city, []):
            if len(hotels) >= target_total:
                break
            if not register_name(city, name):
                continue
            hotels.append({
                "id": next_id(code),
                "city": code,
                "country": country,
                "name": name,
                "stars": stars,
                "price_per_night": make_price(prange[0], prange[1], stars),
                "pets_allowed": None,
                "check_in_time": None,
            })

    brand_list = list(BRAND_TEMPLATES.items())
    city_index = 0
    while len(hotels) < target_total:
        city, country, vibe, prange = HOTEL_CITIES[city_index % len(HOTEL_CITIES)]
        code = city_code(city)
        city_index += 1
        for brand_key, (tpl, stars) in brand_list:
            if len(hotels) >= target_total:
                break
            short_city = city.split("-")[0].split(" ")[0]
            name = tpl.format(city=short_city)
            if not register_name(city, name):
                continue
            hotels.append({
                "id": next_id(code),
                "city": code,
                "country": country,
                "name": name,
                "stars": stars,
                "price_per_night": make_price(prange[0], prange[1], stars),
                "pets_allowed": None,
                "check_in_time": None,
            })

    target_pets = round(len(hotels) * pets_ratio)
    idx = list(range(len(hotels)))
    random.shuffle(idx)
    pets_set = set(idx[:target_pets])
    for i, h in enumerate(hotels):
        h["pets_allowed"] = 1 if i in pets_set else 0

    for h in hotels:
        h["check_in_time"] = random.choice(["14:00", "15:00"])

    ids = [h["id"] for h in hotels]
    assert len(hotels) == target_total
    assert len(ids) == len(set(ids))
    assert all(isinstance(h["price_per_night"], int) and h["price_per_night"] > 0 for h in hotels)
    assert all(h["stars"] in (3, 4, 5) for h in hotels)
    assert all(h["check_in_time"] in ("14:00", "15:00") for h in hotels)
    assert all(h["pets_allowed"] in (0, 1) for h in hotels)
    assert all(h["city"].isupper() and len(h["city"]) in (3, 4) for h in hotels)

    expected_codes = {city_code(c[0]) for c in HOTEL_CITIES}
    actual_codes = {h["city"] for h in hotels}
    assert not (expected_codes - actual_codes)

    for required in ("MIL", "MUC"):
        assert sum(1 for h in hotels if h["city"] == required) > 0

    hotels.sort(key=lambda x: x["id"])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(hotels, f, ensure_ascii=False, indent=2)
    return hotels

# ===============================================================
# ЧАСТЬ 2: ГЕНЕРАЦИЯ ТРАНСПОРТА
# ===============================================================
def generate_transports(
    year: int = 2026,
    min_per_day: int = 4,
    max_per_day: int = 8,
    out_path: str = "transports.json",
) -> list:
    days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365

    PREFERRED_ARRIVAL = (11 * 60 + 30, 16 * 60)
    FULL_ARRIVAL = (7 * 60, 23 * 60)
    PREFERRED_SHARE_MIN = 0.45
    PREFERRED_SHARE_MAX = 0.55

    ORIGINS = {
        "Москва":          (36000, 55000),
        "Санкт-Петербург": (42000, 62000),
        "Казань":          (42000, 62000),
        "Екатеринбург":    (46000, 68000),
    }

    DESTINATIONS = [
        ("Париж", "schengen"), ("Рим", "schengen"), ("Ницца", "schengen"),
        ("Барселона", "schengen"), ("Инсбрук", "schengen"), ("Церматт", "schengen"),
        ("Вена", "schengen"), ("Прага", "schengen"), ("Мюнхен", "schengen"),
        ("Милан", "schengen"), ("Осло", "schengen"), ("Флоренция", "schengen"),
        ("Мадрид", "schengen"), ("Берлин", "schengen"), ("Лондон", "schengen"),
        ("Анси", "schengen"), ("Больцано", "schengen"), ("Интерлакен", "schengen"),
        ("Уиндермир", "schengen"), ("Сан-Марино", "schengen"), ("Виши", "schengen"),
        ("Монтекатини-Терме", "schengen"), ("Баден-Баден", "schengen"),
        ("Бад-Гастайн", "schengen"), ("Бад-Рагац", "schengen"),
        ("Карловы Вары", "schengen"), ("Будапешт", "schengen"),
        ("Сьерра-Невада", "schengen"), ("Шамони-Монблан", "schengen"),
        ("Кортина-д’Ампеццо", "schengen"), ("Гармиш-Партенкирхен", "schengen"),
        ("Андорра-ла-Велья", "schengen"), ("Палермо", "schengen"),
        ("Малага", "schengen"), ("Ханья", "schengen"), ("Фару", "schengen"),
        ("Монте-Карло", "schengen"),
        ("Белград", "serbia"), ("Копаоник", "serbia"), ("Врнячка-Баня", "serbia"),
        ("Будва", "montenegro"), ("Жабляк", "montenegro"),
        ("Сараево", "bosnia"), ("Яхорина", "bosnia"),
        ("Сочи", "russia"), ("Казань", "russia"),
    ]

    TRAIN_CARRIERS = ["РЖД (Фирменный двухэтажный)", "РЖД (Премиум)"]

    preferred_share = random.uniform(PREFERRED_SHARE_MIN, PREFERRED_SHARE_MAX)
    pref_counter = {"preferred": 0, "total": 0}

    def pick_arrival(duration_h: float):
        dur_min = int(round(duration_h * 60))
        pref_counter["total"] += 1
        current_share = pref_counter["preferred"] / pref_counter["total"]
        p_pref = max(0.0, min(1.0, preferred_share - current_share + 0.5))
        use_preferred = random.random() < p_pref
        lo, hi = PREFERRED_ARRIVAL if use_preferred else FULL_ARRIVAL
        arr = random.randint(lo, hi)
        dep = (arr - dur_min) % (24 * 60)
        if use_preferred:
            pref_counter["preferred"] += 1
        return dep, arr % (24 * 60)

    counter = {}

    def make_id(ocode: str, dcode: str, d: date, kind: str = "flight") -> str:
        ds = d.strftime("%y%m%d")
        key = (ocode, dcode, ds, kind)
        n = counter.get(key, 0) + 1
        counter[key] = n
        return f"tr_{ocode.lower()}_{dcode.lower()}_{ds}_{n:02d}"

    def date_str(d: date) -> str:
        return d.strftime("%y-%m-%d")

    def make_flight(origin_name: str, dest_tuple, d: date) -> dict:
        dest_name, d_type = dest_tuple
        o_code = city_code(origin_name)
        d_code = city_code(dest_name)
        price_rng = ORIGINS[origin_name]

        if d_type == "serbia":
            stops = 0 if origin_name in ("Москва", "Казань") else 1
            duration = round(random.uniform(3.0, 3.5), 1)
            carrier = "Air Serbia"
        elif d_type in ("montenegro", "bosnia"):
            stops = 1
            duration = round(random.uniform(4.5, 6.5), 1)
            carrier = "Air Serbia"
        elif d_type == "russia":
            stops = 0
            duration = round(random.uniform(1.5, 4.5), 1)
            carrier = random.choice(["Аэрофлот", "S7 Airlines", "Победа"])
        else:
            stops = 1
            duration = round(random.uniform(6.5, 10.5), 1)
            carrier = random.choice(["Turkish Airlines", "Pegasus Airlines", "FlyOne"])

        price = int(round(random.randint(*price_rng) / 500.0)) * 500
        dep, arr = pick_arrival(duration)

        return {
            "id": make_id(o_code, d_code, d, "flight"),
            "date": date_str(d),
            "origin": o_code,
            "destination": d_code,
            "type": "flight",
            "carrier": carrier,
            "price": price,
            "duration_hours": duration,
            "stops": stops,
            "departure_time": fmt(dep),
            "arrival_time": fmt(arr),
        }

    def make_train(origin_name: str, dest_tuple, d: date) -> dict:
        dest_name, _ = dest_tuple
        o_code = city_code(origin_name)
        d_code = city_code(dest_name)
        duration = round(random.uniform(11.0, 24.0), 1)
        price = int(round(random.randint(3500, 8500) / 100.0)) * 100
        carrier = random.choice(TRAIN_CARRIERS)
        arr = random.randint(*FULL_ARRIVAL)
        dep = (arr - int(round(duration * 60))) % (24 * 60)

        return {
            "id": make_id(o_code, d_code, d, "train"),
            "date": date_str(d),
            "origin": o_code,
            "destination": d_code,
            "type": "train",
            "carrier": carrier,
            "price": price,
            "duration_hours": duration,
            "stops": 0,
            "departure_time": fmt(dep),
            "arrival_time": fmt(arr),
        }

    records = []
    start = date(year, 1, 1)

    for day_offset in range(days_in_year):
        d = start + timedelta(days=day_offset)
        n_today = random.randint(min_per_day, max_per_day)

        for _ in range(n_today):
            for _attempt in range(50):
                o_city = random.choice(list(ORIGINS))
                dest = random.choice(DESTINATIONS)
                d_city, d_type = dest

                if d_type == "russia":
                    if random.random() < 0.4 and o_city in ("Москва", "Санкт-Петербург"):
                        records.append(make_train(o_city, dest, d))
                    else:
                        records.append(make_flight(o_city, dest, d))
                    break
                else:
                    if d_type in ("montenegro", "bosnia") and o_city == "Екатеринбург":
                        continue
                    records.append(make_flight(o_city, dest, d))
                    break

    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids))

    per_day = Counter(r["date"] for r in records)
    assert len(per_day) == days_in_year
    assert all(min_per_day <= c <= max_per_day for c in per_day.values())

    for r in records:
        assert re.fullmatch(r"\d{2}-\d{2}-\d{2}", r["date"])

    assert all(isinstance(r["price"], int) and r["price"] > 0 for r in records)
    assert all(r["type"] in ("flight", "train") for r in records)
    assert all(r["stops"] in (0, 1) for r in records)
    assert all(r["origin"].isupper() and r["destination"].isupper() for r in records)

    for r in records:
        m = to_min(r["arrival_time"])
        assert FULL_ARRIVAL[0] <= m <= FULL_ARRIVAL[1]

    records.sort(key=lambda r: (r["date"], r["id"]))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return records

# ===============================================================
# MAIN
# ===============================================================
if __name__ == "__main__":
    generate_hotels(target_total=1000, pets_ratio=0.40, out_path="hotels.json")
    generate_transports(year=2026, min_per_day=4, max_per_day=8, out_path="transports.json")


import math


random.seed(42)

YEAR = 2026
DAYS_IN_YEAR = 366 if (YEAR % 4 == 0 and (YEAR % 100 != 0 or YEAR % 400 == 0)) else 365

HOTELS_PATH = "hotels.json"
TRANSPORTS_PATH = "transports.json"
OUT_PATH = "weather.json"

# ---------------------------------------------------------------
# 1. Климатические нормы (°C) по кодам городов.
#    Индекс 0 = январь ... 11 = декабрь.
# ---------------------------------------------------------------
CITY_MONTHLY_TEMP = {
    # Россия
    "MOW": [-9.3, -7.7, -2.2, 5.8, 13.1, 16.6, 18.2, 16.4, 11.0, 5.1, -1.2, -6.1],
    "LED": [-4.9, -5.0, -1.0, 5.2, 11.5, 16.1, 19.1, 17.4, 12.4, 6.2, 0.9, -2.5],
    "KZN": [-10.2, -9.5, -3.1, 5.7, 14.1, 18.3, 20.9, 18.6, 12.4, 5.4, -2.1, -7.8],
    "SVX": [-15.5, -13.6, -6.9, 2.7, 10.0, 15.1, 17.2, 14.9, 9.2, 1.2, -6.8, -13.1],
    "AER": [5.9, 6.5, 8.3, 12.1, 16.1, 19.9, 22.7, 22.6, 19.6, 15.1, 11.6, 7.9],
    # Западная Европа
    "CDG": [4.9, 5.6, 8.8, 11.5, 15.2, 18.4, 20.6, 20.5, 16.9, 12.9, 8.1, 5.4],
    "FCO": [7.2, 8.0, 10.5, 13.5, 17.5, 21.5, 24.5, 25.4, 21.5, 17.0, 12.0, 8.2],
    "NCE": [9.5, 10.5, 12.0, 14.5, 18.0, 21.5, 24.0, 24.5, 21.0, 17.5, 13.0, 10.0],
    "BCN": [9.2, 9.9, 11.8, 13.7, 16.9, 20.9, 23.9, 24.4, 21.7, 17.8, 13.0, 10.0],
    "MAD": [6.0, 7.5, 10.5, 12.5, 16.5, 21.5, 25.0, 24.5, 20.5, 15.0, 9.5, 6.5],
    "MIL": [2.5, 4.5, 8.5, 12.5, 17.5, 21.5, 24.5, 23.5, 19.5, 13.5, 7.0, 3.0],
    "BER": [0.5, 1.5, 5.0, 9.5, 14.5, 18.0, 20.0, 19.5, 15.5, 10.5, 5.0, 1.5],
    "MUC": [-1.0, 0.5, 4.5, 9.0, 13.5, 17.0, 19.0, 18.5, 14.5, 9.5, 4.0, 0.0],
    "VIE": [0.5, 2.0, 6.0, 11.0, 16.0, 19.5, 21.5, 21.0, 16.5, 11.0, 5.0, 1.5],
    "PRG": [-0.5, 1.0, 4.5, 9.5, 14.5, 17.5, 19.5, 19.0, 15.0, 9.5, 4.0, 0.5],
    "ZRH": [0.0, 1.0, 5.0, 9.0, 13.5, 17.0, 19.0, 18.5, 14.5, 10.0, 4.5, 1.0],
    "INN": [-2.0, 0.0, 4.5, 9.0, 13.5, 17.0, 18.5, 18.0, 14.0, 9.0, 3.0, -1.0],
    "LON": [5.0, 5.5, 7.5, 10.0, 13.5, 16.5, 18.5, 18.0, 15.5, 12.0, 8.0, 5.5],
    "OSL": [-4.0, -3.5, 0.0, 4.5, 10.0, 14.5, 16.5, 15.5, 11.5, 6.5, 1.0, -2.5],
    # Балканы
    "BEG": [1.0, 3.0, 8.0, 13.0, 18.0, 21.5, 23.5, 23.0, 19.0, 13.5, 7.0, 2.5],
    "SJJ": [0.5, 2.5, 7.0, 11.5, 16.0, 19.5, 21.5, 21.0, 17.0, 12.0, 6.0, 1.5],
    "TIV": [8.0, 8.5, 11.0, 14.5, 19.0, 23.0, 25.5, 25.5, 21.5, 17.0, 12.5, 9.0],
    "KOP": [-3.0, -2.0, 2.0, 6.5, 11.5, 15.0, 17.0, 16.5, 12.5, 7.5, 2.0, -2.0],
    "ZBL": [-2.5, -1.5, 2.5, 7.0, 12.0, 15.5, 17.5, 17.0, 13.0, 8.0, 2.5, -1.5],
    "JAH": [-2.0, -1.0, 3.0, 7.5, 12.5, 16.0, 18.0, 17.5, 13.5, 8.5, 3.0, -1.0],
    "VRN": [0.0, 2.0, 7.0, 12.0, 17.0, 20.5, 22.5, 22.0, 18.0, 12.5, 6.0, 1.5],
    # СПА / природа
    "VHY": [3.5, 5.0, 8.5, 11.5, 15.5, 19.0, 21.5, 21.0, 17.5, 13.0, 7.5, 4.5],
    "MTC": [5.0, 6.5, 10.0, 13.5, 17.5, 21.5, 24.0, 23.5, 20.0, 15.0, 9.5, 6.0],
    "BAD": [0.5, 2.0, 6.0, 10.5, 15.0, 18.5, 20.5, 20.0, 16.0, 11.0, 5.5, 2.0],
    "BGS": [-3.5, -2.0, 1.5, 6.0, 11.0, 14.5, 16.5, 16.0, 12.0, 7.0, 1.5, -2.5],
    "BRG": [-1.0, 0.5, 4.5, 8.5, 13.0, 16.5, 18.5, 18.0, 14.0, 9.5, 4.0, 0.5],
    "KLV": [-2.5, -1.0, 3.0, 7.5, 12.5, 16.0, 18.0, 17.5, 13.5, 8.5, 3.0, -1.5],
    "BUD": [0.5, 2.5, 7.5, 12.5, 17.5, 21.0, 23.0, 22.5, 18.5, 13.0, 6.5, 2.0],
    "ANC": [0.5, 2.0, 6.0, 10.0, 14.5, 18.0, 20.0, 19.5, 15.5, 11.0, 5.5, 1.5],
    "BOL": [-1.0, 1.0, 5.5, 10.0, 14.5, 18.0, 20.0, 19.5, 15.5, 10.5, 4.5, 0.0],
    "INT": [-1.5, 0.0, 4.0, 8.0, 12.5, 16.0, 18.0, 17.5, 13.5, 9.0, 3.5, -0.5],
    "WND": [4.0, 4.5, 6.5, 9.0, 12.5, 15.5, 17.5, 17.0, 14.5, 11.0, 7.0, 4.5],
    "SMA": [3.0, 4.5, 8.5, 12.5, 17.0, 21.0, 23.5, 23.0, 19.0, 14.0, 8.5, 4.5],
    "GRX": [3.5, 5.0, 8.0, 10.5, 14.5, 19.5, 23.5, 23.0, 18.5, 13.0, 7.5, 4.5],
    "CMF": [-2.0, -0.5, 3.5, 7.5, 12.0, 15.5, 17.5, 17.0, 13.0, 8.5, 3.0, -1.0],
    "CORT": [-3.0, -1.5, 2.0, 6.0, 10.5, 14.0, 16.0, 15.5, 11.5, 6.5, 1.5, -2.5],
    "GPI": [-3.5, -2.0, 1.5, 6.0, 10.5, 14.0, 16.0, 15.5, 11.5, 7.0, 1.5, -2.5],
    "AND": [-1.0, 0.5, 4.5, 8.5, 13.0, 17.0, 19.5, 19.0, 15.0, 10.0, 4.0, 0.0],
    "PMO": [10.5, 11.0, 13.0, 15.5, 19.5, 23.5, 26.0, 26.5, 23.5, 19.5, 15.0, 11.5],
    "AGP": [12.0, 12.5, 14.0, 16.0, 19.5, 23.5, 26.0, 26.5, 23.5, 19.5, 15.5, 13.0],
    "CHQ": [12.0, 12.0, 13.5, 16.5, 20.5, 24.5, 26.5, 26.5, 23.5, 19.5, 16.0, 13.0],
    "FAO": [12.0, 12.5, 14.5, 16.0, 18.5, 22.0, 24.0, 24.0, 22.0, 18.5, 15.0, 12.5],
    "MCM": [9.5, 10.0, 12.0, 14.5, 18.0, 21.5, 24.0, 24.0, 21.0, 17.0, 13.0, 10.0],
}

# ---------------------------------------------------------------
# 2. Средняя температура моря (°C) по месяцам — только для приморских городов.
#    Индекс 0 = январь ... 11 = декабрь.
# ---------------------------------------------------------------
SEA_MONTHLY_TEMP = {
    "AER": [10, 10, 11, 13, 17, 22, 25, 26, 24, 20, 16, 12],      # Сочи
    "NCE": [13, 13, 13, 14, 17, 21, 23, 24, 22, 20, 17, 14],     # Ницца
    "BCN": [13, 13, 13, 14, 17, 21, 24, 25, 24, 21, 17, 14],     # Барселона
    "AGP": [15, 15, 15, 16, 18, 21, 23, 24, 23, 21, 18, 16],     # Малага
    "PMO": [14, 14, 14, 15, 18, 22, 25, 26, 25, 22, 19, 16],     # Палермо
    "CHQ": [16, 16, 16, 17, 19, 22, 24, 25, 24, 22, 20, 17],     # Ханья
    "FAO": [15, 15, 15, 16, 18, 20, 21, 22, 21, 20, 18, 16],     # Фару
    "MCM": [13, 13, 13, 14, 17, 21, 23, 24, 22, 20, 17, 14],     # Монте-Карло
    "TIV": [14, 14, 14, 15, 18, 22, 25, 26, 24, 21, 18, 15],     # Будва
}

# ---------------------------------------------------------------
# 3. Горы: для города — (средняя высота зоны катания, поправка °C на 1000 м).
#    Поправка ~6.5°C/1000 м. mountain_temp_c = avg_temp_c - (alt/1000)*6.5.
# ---------------------------------------------------------------
CITY_MOUNTAINS = {
    "CMF": 1900,   # Шамони
    "CORT": 2100,  # Кортина
    "GPI": 1200,   # Гармиш (Цугшпитце рядом)
    "ZRH": 1600,   # Церматт (в долине 1600)
    "INN": 900,    # Инсбрук (Nordkette)
    "KOP": 1800,   # Копаоник
    "ZBL": 1450,   # Жабляк
    "JAH": 1500,   # Яхорина
    "GRX": 2100,   # Сьерра-Невада
    "AND": 1800,   # Андорра-ла-Велья
    "BGS": 1000,   # Бад-Гастайн
    "BRG": 800,    # Бад-Рагац
    "BOL": 500,    # Больцано (Доломиты рядом)
    "INT": 800,    # Интерлакен
    "ANC": 800,    # Анси
    "KLV": 500,    # Карловы Вары (холмы)
}

# ---------------------------------------------------------------
# 4. Ski-города (для сезона и снега).
# ---------------------------------------------------------------
SKI_CODES = {"CMF", "CORT", "GPI", "ZRH", "INN", "KOP", "ZBL", "JAH", "GRX", "AND", "BGS", "BRG"}


def season_of(month: int, code: str) -> str:
    if code in SKI_CODES:
        if month in (11, 12, 1, 2, 3):
            return "winter"
        if month in (4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "autumn"
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def smooth_temp(code: str, d: date) -> float:
    """Средняя температура дня: плавная интерполяция между месяцами + шум."""
    monthly = CITY_MONTHLY_TEMP[code]
    m = d.month
    base = monthly[m - 1]
    day_frac = (d.day - 1) / 30.0
    prev_base = monthly[(m - 2) % 12]
    next_base = monthly[m % 12]

    if d.day <= 15:
        interp = base * (1 - day_frac * 0.3) + prev_base * (day_frac * 0.3)
    else:
        interp = base * (1 - (day_frac - 0.5) * 0.4) + next_base * ((day_frac - 0.5) * 0.4)

    noise = random.uniform(-1.5, 1.5)
    return round(interp + noise, 1)


def snow_depth(code: str, d: date, avg_temp_c: float) -> float:
    """
    Глубина снега в см на конкретный день.
    Логика: снег лежит, если avg_temp_c <= 2°C и город ski/горный/северный.
    Глубина зависит от месяца и широты/высоты, сглаживается по дням.
    """
    # Кто в принципе может иметь снег
    snowy_codes = SKI_CODES | {"MOW", "LED", "KZN", "SVX", "OSL", "MUC", "BER", "PRG",
                               "VIE", "ZRH", "INN", "BGS", "BRG", "KLV", "BAD"}
    if code not in snowy_codes:
        return 0.0
    if avg_temp_c > 2.0:
        return 0.0

    # Базовая глубина по месяцу (для ski-городов — больше)
    m = d.month
    # Зимние месяцы: декабрь–март
    if m in (12, 1, 2, 3):
        if code in SKI_CODES:
            base = random.uniform(40, 120)
        elif code in ("MOW", "LED", "KZN", "SVX", "OSL"):
            base = random.uniform(15, 45)
        else:
            base = random.uniform(5, 25)
    elif m in (11, 4):
        if code in SKI_CODES:
            base = random.uniform(10, 40)
        else:
            base = random.uniform(0, 10)
    else:
        return 0.0

    # Плавность: ближе к середине зимы — больше
    if m in (1, 2):
        factor = 1.2
    elif m in (12, 3):
        factor = 0.8
    else:
        factor = 0.5

    return round(base * factor, 1)


def sea_temp(code: str, month: int):
    """Средняя температура моря в этом месяце или None, если моря нет."""
    if code in SEA_MONTHLY_TEMP:
        return SEA_MONTHLY_TEMP[code][month - 1]
    return None


def mountain_temp(code: str, avg_temp_c: float):
    """Температура в горах (на высоте зоны катания) или None, если гор нет."""
    if code not in CITY_MOUNTAINS:
        return None
    alt = CITY_MOUNTAINS[code]
    # -6.5°C на 1000 м
    return round(avg_temp_c - (alt / 1000.0) * 6.5, 1)


# ---------------------------------------------------------------
# 5. Читаем справочники городов/стран из уже существующих файлов.
# ---------------------------------------------------------------
def load_city_country_map():
    """Возвращает {code: (city_name, country)} из hotels.json."""
    with open(HOTELS_PATH, encoding="utf-8") as f:
        hotels = json.load(f)
    mapping = {}
    for h in hotels:
        mapping[h["city"]] = (h.get("city_name", h["city"]), h["country"])
    return mapping


def load_codes_from_transports():
    """Возвращает множество кодов городов, встречающихся в transports.json."""
    with open(TRANSPORTS_PATH, encoding="utf-8") as f:
        transports = json.load(f)
    codes = set()
    for t in transports:
        codes.add(t["origin"])
        codes.add(t["destination"])
    return codes


# ---------------------------------------------------------------
# 6. Генерация
# ---------------------------------------------------------------
def generate_weather(out_path: str = OUT_PATH) -> list:
    city_country = load_city_country_map()
    transport_codes = load_codes_from_transports()

    # Берём объединение: все города из отелей + все, что есть в транспорте
    all_codes = set(CITY_MONTHLY_TEMP.keys())

    missing_climate = all_codes - set(CITY_MONTHLY_TEMP.keys())
    assert not missing_climate, f"Нет климатических норм для: {missing_climate}"

    records = []
    start = date(YEAR, 1, 1)

    for offset in range(DAYS_IN_YEAR):
        d = start + timedelta(days=offset)
        month = d.month
        date_s = d.strftime("%y-%m-%d")

        for code in sorted(all_codes):
            avg_t = smooth_temp(code, d)
            city_name, country = city_country.get(code, (code, ""))

            rec = {
                "city": code,
                "city_name": city_name,
                "country": country,
                "season": season_of(month, code),
                "month": month,
                "date": date_s,
                "avg_temp_c": avg_t,
                "sea_temp_c": sea_temp(code, month),          # None, если моря нет
                "snow_depth_cm": snow_depth(code, d, avg_t),  # 0.0, если снега нет
                "mountain_temp_c": mountain_temp(code, avg_t),# None, если гор нет
            }
            records.append(rec)

    # -----------------------------------------------------------
    # Валидация
    # -----------------------------------------------------------
    for r in records:
        assert re.fullmatch(r"\d{2}-\d{2}-\d{2}", r["date"])
        assert -30 <= r["avg_temp_c"] <= 40, f"Температура вне разумных пределов: {r}"
        assert r["season"] in ("winter", "spring", "summer", "autumn")
        assert r["sea_temp_c"] is None or 0 <= r["sea_temp_c"] <= 32
        assert 0.0 <= r["snow_depth_cm"] <= 200
        if r["mountain_temp_c"] is not None:
            assert -35 <= r["mountain_temp_c"] <= 30

    # Москва 15 ноября — не +25
    nov_mow = [r for r in records if r["city"] == "MOW" and r["date"].endswith("-11-15")]
    assert len(nov_mow) == 1
    assert nov_mow[0]["avg_temp_c"] < 5, \
        f"Москва 15 ноября: {nov_mow[0]['avg_temp_c']}°C — слишком тепло!"

    # В Сочи в июле море тёплое
    jul_aer = [r for r in records if r["city"] == "AER" and r["date"].endswith("-07-15")][0]
    assert jul_aer["sea_temp_c"] >= 22, f"Сочи в июле море: {jul_aer['sea_temp_c']}°C"

    # В Церматте в январе есть снег и горная температура ниже средней
    jan_zrh = [r for r in records if r["city"] == "ZRH" and r["date"].endswith("-01-15")][0]
    assert jan_zrh["snow_depth_cm"] > 0, "Церматт в январе без снега!"
    assert jan_zrh["mountain_temp_c"] is not None
    assert jan_zrh["mountain_temp_c"] < jan_zrh["avg_temp_c"]

    records.sort(key=lambda r: (r["date"], r["city"]))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return records


if __name__ == "__main__":
    generate_weather(OUT_PATH)