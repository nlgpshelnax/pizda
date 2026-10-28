import sqlite3
import pandas as pd
import numpy as np
import json

DB_NAME = "travel.db"
JSON_FILE = "ds_contract_master.json"
M_WEIGHT = 5  # Вес страновой медианы (сила сглаживания)


def smooth_value(city_values, country_value, m=5):
    """
    Байесовское сглаживание.
    city_values: массив значений в городе.
    country_value: эталонное значение по стране (медиана, p25, p75).
    m: вес странового значения.
    """
    n = len(city_values)
    if n == 0:
        return country_value
    city_mean = np.mean(city_values)
    smoothed = (n * city_mean + m * country_value) / (n + m)
    return round(smoothed, 2)


def generate_smoothed_contract():
    conn = sqlite3.connect(DB_NAME)

    # Загружаем отели (с русскими названиями) и погоду
    hotels = pd.read_sql("SELECT city_code, city_name_ru, country, price_per_night, pets_allowed, stars FROM hotels",
                         conn)
    weather = pd.read_sql("SELECT city_code, month, avg_temp, sea_temp, snow_depth FROM weather", conn)
    conn.close()

    # --- 1. СТАТИСТИКА ПО СТРАНАМ (ЭТАЛОН) ---
    country_stats = hotels.groupby('country').agg(
        country_median=('price_per_night', 'median'),
        country_p25=('price_per_night', lambda x: np.percentile(x, 25)),
        country_p75=('price_per_night', lambda x: np.percentile(x, 75)),
        country_stars_median=('stars', 'median'),
        country_pets_pct=('pets_allowed', lambda x: x.mean() * 100)
    ).to_dict('index')

    # --- 2. ПОГОДА ПО СТРАНАМ И МЕСЯЦАМ ---
    city_to_country = hotels[['city_code', 'country']].drop_duplicates().set_index('city_code')['country'].to_dict()
    city_to_name = hotels[['city_code', 'city_name_ru']].drop_duplicates().set_index('city_code')[
        'city_name_ru'].to_dict()

    weather['country'] = weather['city_code'].map(city_to_country)
    temp_by_country_month = weather.groupby(['country', 'month']).agg(
        avg_temp=('avg_temp', 'mean'),
        sea_temp=('sea_temp', 'mean'),
        snow_depth=('snow_depth', 'mean')
    ).reset_index()

    temp_dict = {}
    for _, row in temp_by_country_month.iterrows():
        c = row['country']
        m = int(row['month'])
        if c not in temp_dict:
            temp_dict[c] = {}
        temp_dict[c][m] = {
            "avg_temp": round(row['avg_temp'], 1) if pd.notna(row['avg_temp']) else None,
            "sea_temp": round(row['sea_temp'], 1) if pd.notna(row['sea_temp']) else None,
            "snow_depth": round(row['snow_depth'], 1) if pd.notna(row['snow_depth']) else None
        }

    # --- 3. СБОРКА КОНТРАКТА СО СГЛАЖИВАНИЕМ ---
    ds_contract = {}

    for city_code, group in hotels.groupby('city_code'):
        country = group['country'].iloc[0]
        city_name_ru = city_to_name.get(city_code, city_code)

        # Эталонные цифры по стране
        c_stats = country_stats.get(country, {})
        c_median = c_stats.get('country_median', 0)
        c_p25 = c_stats.get('country_p25', 0)
        c_p75 = c_stats.get('country_p75', 0)

        city_prices = group['price_per_night'].values

        # Сглаживаем медиану и перцентили
        smooth_median = smooth_value(city_prices, c_median, M_WEIGHT)

        if len(city_prices) >= 3:
            city_p25 = np.percentile(city_prices, 25)
            city_p75 = np.percentile(city_prices, 75)
        else:
            city_p25 = c_p25
            city_p75 = c_p75

        smooth_p25 = round((len(city_prices) * city_p25 + M_WEIGHT * c_p25) / (len(city_prices) + M_WEIGHT), 2)
        smooth_p75 = round((len(city_prices) * city_p75 + M_WEIGHT * c_p75) / (len(city_prices) + M_WEIGHT), 2)

        ds_contract[city_code] = {
            "name_ru": city_name_ru,
            "country": country,
            "hotel_count": len(group),
            "budget": {
                "median": smooth_median,
                "p25": smooth_p25,
                "p75": smooth_p75
            },
            "stars": {
                "median": int(round(group['stars'].median())) if not group['stars'].isna().all() else int(
                    c_stats.get('country_stars_median', 3))
            },
            "pets": {
                "allowed_pct": round(group['pets_allowed'].mean() * 100, 1)
            },
            "weather": temp_dict.get(country, {})
        }

    # --- 4. СОХРАНЕНИЕ ---
    final_json = {
        "smoothing_meta": {
            "method": "bayesian_smoothing",
            "m_weight": M_WEIGHT,
            "description": "Итоговое значение = (n * городское_значение + 5 * страновое_значение) / (n + 5)"
        },
        "vibe_thresholds": {
            "warm_air": 15,
            "swim_sea": 20,
            "ski_snow": 15
        },
        "cities": ds_contract
    }

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("✅ КОНТРАКТ С БАЙЕСОВСКИМ СГЛАЖИВАНИЕМ И РУССКИМИ НАЗВАНИЯМИ СОХРАНЕН")
    print("=" * 60)
    print(f"Файл: {JSON_FILE}")
    print(f"Параметр сглаживания (m): {M_WEIGHT}")
    print(f"Городов: {len(ds_contract)}")

    # Показываем пример для Сочи
    if 'AER' in ds_contract:
        print("\n📋 ПРИМЕР (Сочи, AER):")
        print(json.dumps(ds_contract['AER'], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    generate_smoothed_contract()