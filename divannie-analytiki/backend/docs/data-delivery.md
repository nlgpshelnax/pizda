# Результат выполнения Backend / Data — версия 0.3.0

План выполнен в части разработки и локальной демонстрации, доступной без внешних учётных данных. Реальная поставка всех компонентов от коммерческих API **не завершена**: ниже перечислены конкретные внешние блокеры. Mock-данные не считаются проверкой поставщиков.

## Реальные проверки подключения — 2026-10-26 21:13 MSK

Проверка сделана после сохранения секрета и обновления runtime до revision 3. Значения credentials в отчёт/Git не включены. Все три успешных обращения выполнены без cache hit, через существующие адаптеры:

| Поставщик | Результат | Граница проверки |
|---|---|---|
| Travelpayouts Data | ok, 1 подходящий cached estimate | MOW → AER, даты относительно дня проверки; доступ к Data API подтверждён, не к Search API/бронированию |
| Open-Meteo | ok, 2 дня прогноза | координаты Сочи, текущий день и следующий |
| OSRM | ok | маршрут между двумя точками Сочи; duration/distance, без тарифа |
| Overpass | HTTP 406, invalid_response | GET и read-only POST к interpreter вернули nginx HTML; это не ошибка токена Travelpayouts |

Полные бандлы, цены для состава гостей и checkout остаются mock. Эти проверки не подтверждают hotel/rail/visa/transfer commercial API и не переключают TRIP_EXTERNAL_MODE по умолчанию.

## Матрица задач D01–D14

| Задача | Реализовано | Что остаётся внешним |
|---|---|---|
| D01 Контракты | OpenAPI, JSON Schema компонентного каталога, примеры HTTP и smoke-потребитель | принятие контракта владельцами AI/UI и их интеграционный прогон |
| D02 Доступ | прочитана официальная документация Travelpayouts, добавлен безопасный параметр token; поля доступа в настройках | Data API token работает; Search API/booking, точный hotel API, разрешённый ЖД/визовый источник ещё не подтверждены |
| D03 Данные | HotelProperty / HotelQuote, scope каждой цены, сегменты, IANA timezone, независимые трансферы, источник/validity, RUB/basis | условия конкретных реальных тарифов должны прийти от поставщиков |
| D04 Адаптеры | async HTTP-клиенты Open-Meteo / OSRM / Overpass / Travelpayouts Data, ошибки, deadline/concurrency/retry | Travelpayouts Data/Open-Meteo/OSRM проверены live; Overpass HTTP 406; остальные контракты проверены синтетическими HTTP-ответами |
| D05 Вертикальный маршрут | полные mock-поездки Москва → Сочи/Казань/Дубай/Хургада; компонентная сборка | полный live-маршрут невозможно подтвердить без hotel/transport/transfer доступа |
| D06 Устойчивость | SQLite TTL cache, отдельные snapshots, явный stale opt-in для исследования; no mock/live mixing | политики TTL/хранения согласовать с лицензиями поставщиков |
| D07 Проверки | суммы, область цены, дети/животные/кресла, вместимость, пересадки, смена терминала, окна подачи, буферы, local offsets | дополнительные правила перевозчиков/отеля, визовое право по реальному источнику |
| D08 Пересборка | сохранённые планы, patch, version/CAS, выбранный отель при совместимости, requote, восстановление | включить в граф роли 1 и показать diff в UI роли 3 |
| D09 Погода | реальный forecast-клиент, явное out_of_coverage, отдельная маркировка mock/forecast | live forecast проверен; проверенная климатология ещё не импортирована |
| D10 Маршруты | OSRM duration/distance без выдуманной цены; независимые тарифы трансферов в каталоге | реальный transfer supplier и его тарифы/наличие |
| D11 Vibe | Overpass POI и explore по справочнику; гипотезы сезонности подписаны | Overpass HTTP 406 и редакторская проверка справочника ролью 5; POI не доказывают комфорт/безопасность |
| D12 Визы / ЖД | профиль citizenship/passport/purpose/transit/duration, честный unknown; mock-ЖД в Казань | официальный/лицензионный источник правил и ЖД API |
| D13 После покупки | immutable demo order, idempotent checkout, заявки и mock pending/confirmed/unavailable | настоящие booking/order IDs и подтверждения поставщиков |
| D14 Качество | 61 pytest checks, 30 data-сценариев, CLI, CI, сборка пакета, HTTP smoke и restore | LLM/UI-evals — владельцы 1/3/4; live-checks коммерческого полного маршрута остаются unrun |

## Устройство кода

- `components.py`: нормализованный каталог и сборка совместимых комбинаций. `compose` отдаёт причины отбраковки, а не превращает любую ошибку в выдуманный вариант.
- `models.py` / `validation.py`: совместимые legacy-бандлы, сегменты и проверки времени/стоимости. `transfer` deprecated, используйте outbound_transfer/inbound_transfer.
- `providers/external.py`: фиксированные адреса провайдеров, запросы только чтения. Клиент не принимает произвольный hostname от пользователя.
- `resilience.py`: context runner, circuit breaker (3 сбоя / 30 сек), snapshots и постоянные наблюдения. Ограничение concurrency — 4 на процесс; breaker не распределён между несколькими worker.
- `cache.py`: TTL storage; `state.py`: планы, demo orders и service requests.
- `routes.py`: data/tools/plans/order API. Это слой данных и хранения, не реализация чата/Blocker/LLM.

## Основные endpoints

| Метод / путь | Назначение |
|---|---|
| POST `/api/v1/bundles/search` | поиск в полном mock-каталоге (6 котировок, 4 направления) |
| POST `/api/v1/bundles/compose` | сборка из отдельных HotelQuote/TransportQuote/TransferQuote |
| POST `/api/v1/bundles/requote` | совместимый stateless endpoint с price delta |
| POST `/api/v1/plans` | создать сохранённый план из TripRequest |
| GET/PATCH `/api/v1/plans/{id}` | прочитать / применить частичный patch с base_version |
| POST `/api/v1/plans/{id}/selection` | выбрать вариант, увеличить версию |
| POST `/api/v1/plans/{id}/checkout` | идемпотентный demo-only заказ |
| GET `/api/v1/orders/{id}` | неизменяемый снимок заказа и total |
| GET/POST `/api/v1/orders/{id}/services` | прочитать / создать заявку услуги |
| POST `/api/v1/orders/{id}/services/{service_id}/simulate` | имитация решения поставщика; только mock |
| POST `/api/v1/tools/{weather,route,places,flights}` | контекст: погода, дорога, POI, cached flight estimates |
| POST `/api/v1/tools/rail` | mock-ЖД; live даёт not_configured |
| POST `/api/v1/tools/entry-rules` | профиль визовой проверки и unknown |
| POST `/api/v1/explore` | направления по месяцу/vibe, без выдуманной точной цены |
| GET `/api/v1/providers` | режимы и наличие конфигурации, без значений credentials |
| GET `/api/v1/metrics` | сохранённые counters, ошибки, cache hits, fallback, p50/p95 |

`ContextResult.status` передаёт статус инструмента; при fallback исходный отказ передаётся в fallback_reason; HTTP 200 инструмента не означает наличие данных. Bundle search использует 503/504 при отказе поставщика. Для stale snapshot указан `stale=true`, исходный срок действия, warning и `fallback_reason`; исходный отказ учитывается в метриках. Circuit-open без свежего cache возвращается явно. Stale никогда не используется для checkout/подтверждённых бандлов.

## Пересборка для роли 1

Создайте план, сохраните его ID и version. PATCH передаёт `base_version` и `changes`, например:

```json
{"base_version":1,"changes":{"check_in":"2026-11-12","check_out":"2026-11-17","guests":{"children_ages":[7]}}}
```

Origin, adults, pets, budget сохранятся. Поле, отсутствующее в changes, не меняется; null удаляет только опциональное значение, например budget. Неизвестные поля/недопустимые значения — 422. CAS выполняется после ожидания provider тоже: старый ответ не перезаписывает новую версию (409). Selection также увеличивает version. Отправляйте текущую версию в checkout.

Если выбранный отель остался пригодным и есть новая точная котировка того же location_id, selection переносится на неё. При отсутствии совместимости выбор очищается. Покупка создаёт отдельный immutable snapshot; последующий patch плана не меняет заказ. `idempotency_key` повторной покупки при том же plan/version возвращает тот же order; конфликт ключа/версии — 409.

Владельцу UI: используйте backend total/Decimal-строки; PATCH разрешён CORS для configured origins. Доступных session/messages/chat endpoint пока нет: граф и диалог — роль 1. Для TypeScript генерируйте типы из `docs/openapi.json`.

## Проверки и инструменты

```bash
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
uv sync --frozen
uv run ruff check .
uv run pytest -q
uv run python scripts/run_data_evals.py
uv run python scripts/catalog.py validate data/fixtures/components.json
uv run python scripts/export_openapi.py
uv build --out-dir .runtime/dist
```

Запуск сервера — как в README. В отдельном терминале:

```bash
uv run python scripts/smoke.py
# Перезапустите только запущенный вами сервер, затем:
uv run python scripts/smoke.py --restore
```

Smoke создаёт отдельный план, demo order и имитацию услуги; IDs в `.runtime/smoke-state.json`. Повторный обычный smoke создаёт новую независимую демонстрацию. Restore читает сохранённые записи. Все операции в smoke используют mock, внешняя сеть не нужна после установки пакетов.

`data/evals/data-cases.json` — 30 сценариев именно данных/стыковок. Runner возвращает exit code 1 при failed или пустом наборе. Проверка самого runner показывает, что заведомо неверное ожидание вызывает failed. Результат `.runtime/data-evals.json` содержит pass/fail и список причин; LLM-качество этим не измеряется.

Импорт собственного каталога: подготовьте JSON по `docs/components.schema.json`, выполните `scripts/catalog.py validate`. Укажите путь в `TRIP_COMPONENT_CATALOG_PATH`, перезапустите приложение и используйте compose. Для полного mock-search исходник Bundle JSON задаётся через `TRIP_CATALOG_PATH`. Текущие MockCatalog и compose принимают только явно synthetic данные; настоящий компонентный импорт требует отдельного live workflow. Не присваивайте настоящим данным kind=mock ради прохождения проверок. Утилита snapshot пишет новый файл эксклюзивно и выводит SHA-256, не перезаписывая существующие данные.

## Настройки / реальные запросы

По умолчанию `TRIP_PROVIDER_MODE=mock` и `TRIP_EXTERNAL_MODE=mock`. В первом режиме нет live-покупок. Второй можно переключить в `live`, чтобы использовать реальные weather/route/places/flight tools. Это **не переключает** hotel/transport bundles в live и не даёт разрешения коммерческого поставщика.

`TRIP_TRAVELPAYOUTS_TOKEN` хранится как SecretStr, используется только в request-scoped X-Access-Token для api.travelpayouts.com, не в URL и не в shared headers клиента. Окружение поддерживает proxy-инъекцию. При отсутствии ключа `/tools/flights` в live возвращает not_configured. Секреты вводятся в настройках среды, не в Git/чат.

Для облака сохранены домены: api.open-meteo.com, router.project-osrm.org, overpass-api.de, api.travelpayouts.com. Первоначальный 403 CONNECT снят после обновления настроек; актуальные результаты live-проверок приведены выше (3 успеха, Overpass HTTP 406). Сохранение черновика не применяет политику автоматически.

`TRIP_STATE_PATH` — SQLite планов/заказов; `TRIP_CACHE_PATH` — cache/snapshots/observations. Они в `.runtime`, игнорируются Git и не должны попадать в исходный архив. Live-процессы после восстановления среды запускаются заново; записи БД сохраняются с filesystem snapshot. Контекстные snapshots могут устареть и допускаются только при явном `allow_stale=true` для исследования.

## Оставшиеся действия вне кода

1. Секрет Data API и сетевые разрешения сохранены, live-read-only проверка Data API прошла. Для Overpass требуется отдельная диагностика HTTP 406; не считать POI-поставщика готовым.
2. Получить конкретные разрешённые API отелей, трансферов, ЖД и визовых правил. Название «Viajante» на доске не является endpoint/договором доступа; пока не идентифицировано.
3. С ролями 1/3 принять контракт data/plans и выполнить их настоящий UI/chat integration. С ролью 5 проверить seasonality/vibe: текущие значения помечены curated_hypothesis, `seasonality_verified=false`, climatology=null.
4. После этого провести live-проверки цен/availability и общие LLM/UI-evals. Настоящая оплата/бронирование по-прежнему не входит в локальный demo backend.
