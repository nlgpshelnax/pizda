# Зависимости и запуск по ролям

## Что уже зафиксировано

Источник Python-зависимостей — `pyproject.toml`, точные разрешённые версии и хеши — `uv.lock`. Python: **3.12.x** (`.python-version`). Для повторяемости используйте **uv 0.12.23** — эту версию использует CI. Файл lock общий для backend, будущего агента и Python-evals.

| Пакет | Для чего | Кому нужен |
|---|---|---|
| FastAPI | REST API и OpenAPI | 1, 2 |
| Uvicorn | сервер разработки | 1, 2, интеграция 3 |
| Pydantic 2 | JSON Schema, слоты, запросы, котировки | 1, 2, 4 |
| pydantic-settings | настройки окружения | 1, 2 |
| httpx | API/LLM-клиенты, HTTP-проверки | 1, 2, 4 |
| pytest | проверки логики и контрактов | 1, 2, 4 |
| Ruff | lint и форматирование Python | 1, 2, 4 |
| hatchling | сборка Python-пакета | автоматически через uv |
| sqlite3, zoneinfo, Decimal | локальное хранение, время, деньги | стандартная библиотека Python |

Точные версии транзитивных библиотек не устанавливайте вручную. Обычная установка — `uv sync --frozen`, а не `pip install` набора последних версий. Исходный запуск mock не требует API-ключей, Node, модели, Docker, Redis, PostgreSQL или GPU.

## Установить инструменты один раз

1. Git: [официальная установка](https://git-scm.com/downloads).
2. Python 3.12: [python.org](https://www.python.org/downloads/) либо управляемая установка uv.
3. uv: [официальная инструкция](https://docs.astral.sh/uv/getting-started/installation/). Выберите pinned release `0.12.23`; проверьте `uv --version`.
4. Для UI — Node.js **24 LTS** и npm из его поставки: [nodejs.org](https://nodejs.org/). Node/Python — разные среды; `npm` не заменяет `uv`.

Если Python 3.12 ещё не установлен, после установки uv выполните `uv python install 3.12`. Скачивание Python/пакетов требует сети; никакой установщик не отключает TLS-проверку. В корпоративной сети настройте доверенный CA по правилам организации.

## Backend: Linux / macOS / WSL / облако

Из корня checkout:

```bash
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
uv sync --frozen
uv run uvicorn trip_data.main:app --host 127.0.0.1 --port 8000
```

Во втором терминале из того же корня:

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/v1/bundles/search \
  -H 'Content-Type: application/json' -d @data/fixtures/search-request.json
```

Ожидается `status=ok`, `catalog_size=6`; поиск возвращает одну опцию, `total.amount="73000.00"`, `DEMO_DATA`. Это искусственный пример, не рыночная цена. Остановка — Ctrl+C. При занятом порте выберите 8001 и согласуйте API URL с UI. Не завершайте чужие процессы.

## Backend: Windows PowerShell

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.runtime/uv-cache'
uv sync --frozen
uv run uvicorn trip_data.main:app --host 127.0.0.1 --port 8000
```

Во втором PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
$body = Get-Content -Raw -Encoding utf8 data/fixtures/search-request.json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/bundles/search -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Не требуется активировать `.venv` вручную: команды запускает `uv run`. Linux-команды проверены в облаке; PowerShell-инструкции приведены для участников команды и не проверялись на Windows в этой среде.

## Проверки Python

Из корня, с тем же `UV_CACHE_DIR`:

```bash
uv run ruff check .
uv run pytest -q
uv run python scripts/export_openapi.py
git diff -- docs/openapi.json
```

Обновление `docs/openapi.json` коммитьте вместе с изменением моделей/API. `uv run ruff format .` может менять файлы: запускайте перед коммитом своих изменений. В исходной версии было 15 тестов; после этапа Data 1 набор расширен, актуальное число показывает pytest; это не evals агента и не проверка UI. Текущий набор может показывать deprecation warning от Starlette/httpx; предупреждение не означает падение тестов, не отключайте проверки из-за него.

## Роль 1: агент / LLM

Для первого детерминированного автомата достаточно существующих Pydantic, httpx, sqlite3 и pytest. Локальная LLM — отдельный процесс, обязательность и модель выбирают роли 1 и 4 по замерам качества/скорости. Не требуется устанавливать SDK каждого провайдера.

Если владелец выбирает LangGraph, **он один** добавляет в своём PR:

```bash
uv add --group agent 'langgraph>=1,<2'
```

Команда обновит `pyproject.toml` и `uv.lock`: оба файла входят в PR. После объединения этого PR остальные устанавливают `uv sync --frozen --group agent`. Пока группы `agent` нет, этот последний вызов выполнять нельзя. Если создаётся отдельный пакет `trip_agent`, роль 1 добавляет его в список пакетов Hatch в `pyproject.toml` и проверяет сборку/импорт после `uv sync` — editable-install текущего `trip_data` сам по себе не объявляет новый пакет.

Рекомендуемый локальный кандидат для эксперимента: Ollama + `qwen3:4b`. Это ещё не выбранный обязательный runtime. Официальная установка: [Ollama](https://ollama.com/download). После установки:

```bash
ollama serve
# В другом терминале:
ollama pull qwen3:4b
ollama list
```

Если приложение Ollama уже запустило сервер, второй `ollama serve` не нужен. API обычно на `127.0.0.1:11434`; вызовы можно делать через существующий httpx. Наличие модели проверяется отдельно от работоспособности backend. Скачивание требует сети, для защиты модель готовят заранее. Потребление RAM/VRAM и latency измеряет роль 1; GPU не гарантирован. Переменные model/base_url вводятся в конфиг только вместе с использующим их кодом; сейчас backend их не читает. Hosted LLM SDK и ключ добавлять только для реально выбранного поставщика.

## Роль 3: frontend

**Frontend пока отсутствует.** Следующие команды — стартовая задача владельца UI, а не запуск уже существующего приложения. Создать каркас один раз из корня после проверки, что каталога `frontend` нет:

```bash
npm create vite@7 frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query@5
npm install --save-dev vitest@3 jsdom@26 @testing-library/react@16 @testing-library/jest-dom@6 @playwright/test@1 openapi-typescript@7
```

Основа: React 19, TypeScript 5, Vite 7; шаблон и installer определяют точные patch-версии, которые надо проверить и сохранить в `frontend/package-lock.json`. Эти npm-зависимости пока **не установлены и не проверены** в репозитории. React Query нужен для server state; CSS Modules входят в Vite и не требуют отдельной библиотеки. Не добавляйте UI kit/state library без нужды.

В первом UI PR владелец добавляет и проверяет scripts: `dev`, `build`, `lint`, `test` (Vitest run), `test:e2e` (Playwright test), `api:types` (`openapi-typescript ../docs/openapi.json -o src/api/schema.d.ts`). Для `test:e2e` нужны Playwright config, тест и доступный backend. Для Vitest — test environment jsdom, setup jest-dom, минимум один содержательный компонентный тест. Scripts не существуют до этого PR.

После появления каркаса и lockfile остальные:

```bash
cd frontend
npm ci
npm run api:types
npm run dev -- --host 127.0.0.1 --port 5173
```

Для браузерных проверок: `npx playwright install chromium`; на Linux CI могут понадобиться системные библиотеки (`npx playwright install --with-deps chromium` в подходящем runner). Не скачивайте браузеры участникам, которые только правят Python/документы. UI обращается к API через `/api` с Vite proxy на `127.0.0.1:8000`; proxy настраивает роль 3. Это проще, чем дублировать backend URL. Если выбран прямой fetch, CORS уже разрешает `http://localhost:5173`; для `http://127.0.0.1:5173` добавьте origin через `TRIP_CORS_ORIGINS` и перезапустите backend.

## Роль 4: QA / evals

Существующего Python dev-окружения достаточно для JSONL, расчёта метрик и pytest. Будущие LLM-evals используют ту же модель/конфиг, что роль 1. Не добавляйте платные платформы evals как обязательную зависимость. Browser evals используют Playwright из **общего frontend-пакета**, отдельный npm-проект не нужен. Команда eval runner появится в PR роли 4 и должна быть описана там; текущий `pytest` оценивает только data-каркас.

## Роль 5: продукт / защита

Для Markdown/CSV/сценариев нужен только Git и текстовый редактор. Презентацию можно готовить любым инструментом, но в репозитории должны остаться текст питча, сценарий, исходные данные и экспорт слайдов или ссылка на доступный источник. Python/Node нужны только если вы сами запускаете прототип. Figma, PowerPoint, Google Slides, Docker не являются обязательными runtime-зависимостями приложения.

## Переменные и общие lockfile

Сейчас поддерживаются `TRIP_PROVIDER_MODE=mock`, `TRIP_CATALOG_PATH`, `TRIP_CORS_ORIGINS`, `TRIP_CACHE_PATH`, `TRIP_CACHE_TTL_SECONDS`, `TRIP_PROVIDER_DEADLINE_SECONDS`; пример — `.env.example`. Копия в `.env` необязательна. Реальные ключи не коммитьте. Каждый новый параметр добавляется одновременно с использующим его кодом, описанием обязательности и безопасным примером.

`uv.lock` обновляет владелец Python-изменения, `frontend/package-lock.json` — владелец UI. При конфликте manifest сначала согласовать зависимости, затем пересобрать lock выбранной версией менеджера и проверить frozen-install; не склеивать конфликт вручную и не удалять lock ради успешной установки. В повседневной работе: `uv sync --frozen`, `npm ci`. `uv add`/`npm install` — при намеренном изменении зависимостей.

Обновление 0.3.0: [полная data-поставка](data-delivery.md). Дополнительных Python-пакетов нет. Новые переменные описаны в `.env.example`: TRIP_EXTERNAL_MODE (mock по умолчанию), TRIP_TRAVELPAYOUTS_TOKEN (секрет), TRIP_STATE_PATH, TRIP_COMPONENT_CATALOG_PATH, TRIP_CONTEXT_FIXTURE_PATH, TRIP_KNOWLEDGE_PATH. Состояние .runtime сохраняется локально и не коммитится.

Версия 0.4.0 использует общую SQLite из стандартной библиотеки: новых пакетов/DB-сервера не нужно. `TRIP_DATABASE_PATH` по умолчанию `.runtime/travel.sqlite3`; state/cache используют этот же путь, если не заданы явные overrides. После `uv sync --frozen` выполните `uv run python scripts/load_database.py`. [Схема/ETL](database.md).
