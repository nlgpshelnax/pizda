# О!дин запрос — общий репозиторий команды

Сервис данных для туристического агента: структурированный запрос → котировки → проверка ограничений и времени → до пяти бандлов. Основа — доска команды; прежний план используется только там, где он ей не противоречит.

**Статус 0.4.0:** общий SQLite-каталог `.runtime/travel.sqlite3`, загрузчик источников, 62 реальных OSM-объекта размещения и 173 POI; погода, маршруты и авиаоценки загружаются через API. Демо-тарифы отделены от реальных карточек. Реальные цены/наличие отелей пока неизвестны. [Архитектура БД, таблицы, загрузка и SQL/API](docs/database.md).

**[Полный результат, матрица D01–D14 и внешние блокеры](docs/data-delivery.md)** · **[Выполненный план](docs/execution-plan.md)**

## Начать работу в команде

**[Общий старт: архив, Git clone и распределение работы](docs/team-start.md)** · **[Все зависимости и установка по ролям](docs/dependencies.md)** · **[Ветки, коммиты и PR](CONTRIBUTING.md)**

| Роль | План работы |
|---|---|
| 1. Lead AI Engineer | [Инструкция: ответственность, код, API и порядок задач](docs/role-1-ai.md) |
| 2. Backend / Data Engineer | [API, данные, бандлы и кэш](docs/role-2-backlog.md) |
| 3. Frontend Developer | [Чат, дашборд, слоты и карточки](docs/role-3-frontend.md) |
| 4. Prompt Engineer / QA & Evals | [Промпты, 30 сценариев и метрики](docs/role-4-qa.md) |
| 5. Product Lead / Pitcher | [База знаний, питч и защита](docs/role-5-product.md) |

[Скачать весь исходный проект ZIP](https://github.com/nlgpshelnax/xyinya/archive/refs/heads/main.zip). Для коммитов используйте clone: архив не содержит Git-историю. AI/UI и LLM-evals ещё предстоит реализовать их владельцам; data-сценарии и сквозной backend smoke уже есть.

## Запуск

Нужны Python 3.12 и uv. Команды выполняются из корня репозитория:

```bash
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
uv sync --frozen
uv run python scripts/load_database.py
uv run uvicorn trip_data.main:app --host 127.0.0.1 --port 8000
```

В другом терминале:

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/v1/bundles/search \
  -H 'Content-Type: application/json' -d @data/fixtures/search-request.json
```

Ответ содержит `plan_version`, `options`, `rejected`, `limitations`. Успешный пример возвращает один бандл с общей суммой `73000.00`, меткой `mock` и предупреждением `DEMO_DATA`. Даты/гости вне покрытия дают пустой список с причиной; API не подставляет старую цену. Некорректный запрос даёт 422.

**[Как агент читает БД и как она наполняется автоматически](docs/database-first.md)** — источники, загрузчики, DB-only API и оставшиеся этапы.

[Схема, синхронизация и запрос тура для агента](docs/agent-data-contract.md).

**[Xotelo: отели и ориентировочные цены без ключа](docs/xotelo.md)**.

[Найденные источники тарифов и виз, подтверждённый доступ и дальнейшие шаги](docs/sources-and-access.md).

[Европейский live ETL и ограничения источников](docs/europe-live-sync.md).

## Загрузить данные в общую базу

```bash
uv run python scripts/load_database.py --online
```

Обновить OSM и API: добавьте `--refresh-hotels`. Публичный каталог: `GET /api/v1/catalog`; поиск реальных объектов: `POST /api/v1/hotels/search`. Снимок SQLite без планов/заказов: `uv run python scripts/export_database.py --output .runtime/catalog-export.sqlite3`. Ключи — только в секретах среды. [Подробная схема](docs/database.md).

[Репетиция трёх сценариев и инструкция для защиты](docs/demo-backend.md).

[Инструкция по контрактам для агента и UI](docs/integration-handoff.md).

## Проверки

```bash
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
uv run ruff check .
uv run pytest -q
uv run python scripts/export_openapi.py
uv run python scripts/run_data_evals.py
```

`docs/openapi.json` — контракт для AI и frontend. При изменении моделей перегенерируйте схему. CI проверяет lint, тесты и актуальность OpenAPI. Интернет и ключи для этих проверок не нужны после установки зависимостей.

## Структура

```text
backend/src/trip_data/
  models.py            # общие контракты и происхождение данных
  validation.py        # деньги, ограничения, временные стыковки
  cache.py             # SQLite TTL cache
  service.py           # сборка результатов, отбраковка, top-5
  providers/catalog.py # интерфейс каталога и mock-реализация
  main.py              # FastAPI и OpenAPI
backend/tests/         # проверки API, цен и стыковок
data/fixtures/         # синтетический каталог, запрос поиска и пример requote
docs/                  # архитектура, интеграции, план вашей роли
scripts/               # генерация контракта
```

После запуска сервера: `uv run python scripts/smoke.py`. После перезапуска: `uv run python scripts/smoke.py --restore`. Поиск и компонентная сборка покрывают Сочи, Казань (ЖД), Дубай и Хургаду. Все котировки synthetic; общей живой цены это не подтверждает.

Текущие контракты, инструменты и ограничения: [поставка Backend/Data](docs/data-delivery.md). [Этап 1](docs/data-milestone-1.md) сохранён как история версии 0.2.0.

Начните с [архитектуры](docs/architecture.md), затем [плана роли №2](docs/role-2-backlog.md) и [матрицы поставщиков](docs/providers.md). [Контракт API](docs/contracts.md) нужен всем участникам.

## Границы демо

Это локальный сервис разработки без авторизации; не публикуйте его в интернет как production API. Никаких реальных бронирований, платежей или утверждений о наличии мест. Бандлы и оформление работают только в `mock`. Контекстные tools можно отдельно включить через `TRIP_EXTERNAL_MODE=live`; это не делает цены/наличие бандлов реальными. Для разных валют сначала нужен проверяемый FX-контракт — текущий MVP принимает только RUB.

Автоматизация обновления, альтернативный hotel API и импорт прайс-листов: [статус роли 2](docs/role-2-final-status.md).
