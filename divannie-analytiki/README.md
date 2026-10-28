# 🏖️ AI-Агент для подбора путешествий «О!дин запрос» (Travel-Tech Agent)

Интеллектуальный туристический AI-агент, разработанный для хакатона. Проект реализует гибридную архитектуру: детерминированный конечный автомат (State Machine) на базе Python управляет бизнес-логикой и бронированием, а локальная языковая модель **Qwen 2.5** отвечает за лингвистический анализ (NLU), извлечение слотов и Explainability.

---

## 🏗️ Архитектура и стек
* **Ядро (State Machine):** `core/workflow.py` (управление шагами, Blocker Guard, Surgical Invalidation, разрешение конфликтов бюджета).
* **NLU / Модель:** Локальный запуск **Qwen 2.5 (3B / 7B)** через Ollama (OpenAI-compatible API).
* **База данных:** SQLite (`travel.db`) + мастер-контракт эвристик (`ds_contract_master.json`) с байесовским сглаживанием цен и климатическими порогами.
* **Интерфейс:** Консольный интерактивный чат (`cli_chat.py`).

---

## 📂 Структура проекта
```text
divannie-analytiki/
├── core/
│   ├── workflow.py         # Главный оркестратор (State Machine)
│   ├── llm_client.py       # Интеграционный клиент Qwen 2.5 + Regex Fallback
│   ├── local_db_tools.py   # Прямые инструменты чтения SQLite-базы (travel.db)
│   ├── state.py            # Pydantic-модели состояния и слотов
│   ├── tools_interface.py  # Абстрактные контракты данных (Bundle, Hotel, Transport)
│   └── mock_tools.py       # Резервные мок-данные
├── prompts/                # Промпты для Qwen (NLU, генерация вопросов, Explainability)
├── backend/                # Сервисы и скрипты ETL-сборки бэкенда
├── travel.db               # Локальная SQLite база данных каталога
├── ds_contract_master.json # Мастер-контракт эвристик климата и цен
├── cli_chat.py             # Консольный чат для проверки сценариев
├── benchmark.py            # Автоматическая оценка метрик качества
└── requirements.txt        # Зависимости проекта