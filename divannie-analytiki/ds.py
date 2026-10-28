import sqlite3
import json
import os
import pandas as pd
import numpy as np

DB_NAME = "travel.db"
HOTELS_FILE = "hotels.json"
TRANSPORTS_FILE = "transports.json"
WEATHER_FILE = "weather.json"

# Твой словарь (переворачиваем: код -> название)
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

# Переворачиваем: {"MOW": "Москва", ...}
CODE_TO_NAME = {code: name for name, code in CITY_CODES.items()}


def load_json(filepath):
    if not os.path.exists(filepath):
        print(f"❌ Файл {filepath} не найден!")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
            for k in ["data", "items", "results"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
            return []
        return data


def get_val(item, keys, default=None):
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS hotels;
    DROP TABLE IF EXISTS transport;
    DROP TABLE IF EXISTS weather;
    DROP TABLE IF EXISTS cities;

    CREATE TABLE cities (
        code TEXT PRIMARY KEY,
        name_ru TEXT
    );

    CREATE TABLE hotels (
        id TEXT PRIMARY KEY, 
        city_code TEXT, 
        city_name_ru TEXT,
        country TEXT, 
        name TEXT, 
        stars INTEGER, 
        price_per_night REAL, 
        pets_allowed INTEGER, 
        check_in_time TEXT
    );

    CREATE TABLE transport (
        id TEXT PRIMARY KEY, 
        date TEXT, 
        origin_code TEXT, 
        origin_name_ru TEXT,
        destination_code TEXT, 
        destination_name_ru TEXT,
        type TEXT, 
        carrier TEXT, 
        price REAL, 
        duration_hours REAL, 
        stops INTEGER, 
        departure_time TEXT, 
        arrival_time TEXT
    );

    CREATE TABLE weather (
        city_code TEXT, 
        month INTEGER, 
        avg_temp REAL, 
        sea_temp REAL, 
        snow_depth REAL,
        PRIMARY KEY (city_code, month)
    );
    """)
    conn.commit()
    return conn


def build_db():
    if os.path.exists(DB_NAME): os.remove(DB_NAME)
    conn = init_db()
    cur = conn.cursor()

    # --- 1. ЗАГРУЖАЕМ СПРАВОЧНИК ГОРОДОВ ---
    print("1. Загружаем справочник городов...")
    for name_ru, code in CITY_CODES.items():
        cur.execute("INSERT OR IGNORE INTO cities (code, name_ru) VALUES (?, ?)", (code, name_ru))
    conn.commit()
    print(f"   ✅ Загружено городов: {len(CITY_CODES)}")

    # --- 2. ЗАГРУЖАЕМ ОТЕЛИ ---
    print("2. Загружаем отели...")
    hotels_data = load_json(HOTELS_FILE)
    for h in hotels_data:
        city_code = get_val(h, ["city", "city_code"])
        city_name_ru = CODE_TO_NAME.get(city_code, city_code)

        cur.execute("""
            INSERT OR IGNORE INTO hotels (id, city_code, city_name_ru, country, name, stars, price_per_night, pets_allowed, check_in_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            get_val(h, ["id"]),
            city_code,
            city_name_ru,
            get_val(h, ["country"]),
            get_val(h, ["name"]),
            get_val(h, ["stars"]),
            get_val(h, ["price_per_night"]),
            get_val(h, ["pets_allowed"]),
            get_val(h, ["check_in_time"])
        ))
    conn.commit()
    print(f"   ✅ Загружено отелей: {len(hotels_data)}")

    # --- 3. ЗАГРУЖАЕМ ТРАНСПОРТ ---
    print("3. Загружаем транспорт...")
    transports_data = load_json(TRANSPORTS_FILE)
    for t in transports_data:
        origin_code = get_val(t, ["origin"])
        dest_code = get_val(t, ["destination"])

        origin_name_ru = CODE_TO_NAME.get(origin_code, origin_code)
        dest_name_ru = CODE_TO_NAME.get(dest_code, dest_code)

        cur.execute("""
            INSERT OR IGNORE INTO transport (id, date, origin_code, origin_name_ru, destination_code, destination_name_ru, type, carrier, price, duration_hours, stops, departure_time, arrival_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            get_val(t, ["id"]),
            get_val(t, ["date"]),
            origin_code,
            origin_name_ru,
            dest_code,
            dest_name_ru,
            get_val(t, ["type"]),
            get_val(t, ["carrier"]),
            get_val(t, ["price"]),
            get_val(t, ["duration_hours"]),
            get_val(t, ["stops"]),
            get_val(t, ["departure_time"]),
            get_val(t, ["arrival_time"])
        ))
    conn.commit()
    print(f"   ✅ Загружено транспорта: {len(transports_data)}")

    # --- 4. ЗАГРУЖАЕМ ПОГОДУ ---
    print("4. Загружаем и агрегируем погоду...")
    weather_data = load_json(WEATHER_FILE)

    agg = {}
    for w in weather_data:
        city_code = get_val(w, ["city"])
        month = get_val(w, ["month"])
        if not city_code or not month:
            continue

        key = (city_code, int(month))
        if key not in agg:
            agg[key] = {"avg": [], "sea": [], "snow": []}

        avg_t = get_val(w, ["avg_temp_c", "avg_temp"])
        if avg_t is not None: agg[key]["avg"].append(avg_t)

        sea_t = get_val(w, ["sea_temp_c", "sea_temp"])
        if sea_t is not None: agg[key]["sea"].append(sea_t)

        snow = get_val(w, ["snow_depth_cm", "snow_depth"])
        if snow is not None: agg[key]["snow"].append(snow)

    for (city_code, month), vals in agg.items():
        avg_temp = np.mean(vals["avg"]) if vals["avg"] else None
        sea_temp = np.mean(vals["sea"]) if vals["sea"] else None
        snow = np.mean(vals["snow"]) if vals["snow"] else None

        cur.execute("""
            INSERT INTO weather (city_code, month, avg_temp, sea_temp, snow_depth)
            VALUES (?, ?, ?, ?, ?)
        """, (city_code, month,
              round(avg_temp, 1) if avg_temp else None,
              round(sea_temp, 1) if sea_temp else None,
              round(snow, 1) if snow else None))

    conn.commit()
    print(f"   ✅ Агрегировано в {len(agg)} записей (город-месяц)")

    # --- 5. АУДИТ ---
    print("\n" + "=" * 50)
    print("📊 АУДИТ")
    print("=" * 50)

    df_hotels = pd.read_sql("SELECT * FROM hotels LIMIT 3", conn)
    df_trans = pd.read_sql("SELECT * FROM transport LIMIT 3", conn)

    print("\n🏨 Примеры отелей (код -> название):")
    print(df_hotels[['city_code', 'city_name_ru']].to_string(index=False))

    print("\n✈️ Примеры рейсов (откуда -> куда):")
    print(df_trans[['origin_code', 'origin_name_ru', 'destination_code', 'destination_name_ru']].to_string(index=False))

    print("\n✅ Готово! Теперь в базе есть и коды, и русские названия.")


if __name__ == "__main__":
    build_db()