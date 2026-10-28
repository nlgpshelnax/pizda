# Подключение бэкенда: аудит и предлагаемая граница

Проверено 28 октября 2026. **Ни один JSON ниже не является согласованным API команды. Это предложение. Реальные URL, методы авторизации и эндпоинты неизвестны. HTTP-адаптер и сервер не создавались.**

## Что уже есть

`src/types.ts` задаёт `AgentAdapter.respond(request): Promise<AgentResponse>`. `App` теперь принимает необязательный `agentAdapter` и передаёт его в `useTravelSession`. Без него работает прежний MockAgentAdapter. Передавать нужно стабильный экземпляр, созданный один раз вне React-рендера:

```tsx
// После согласования API и реализации проверенного командой HTTP-адаптера:
// const teamAdapter: AgentAdapter = ...;
// <App agentAdapter={teamAdapter} />
```

Это точка замены **только обработки сообщений**, не всей системы бронирования. UI-компоненты не создают адаптер и не импортируют `data/trips`. Ответ применяется через `state/session.ts:applyResponse`. История пополняется локально; ID сообщений создаёт браузер. Уже есть busy, обработка ошибки с сохранением параметров, игнорирование запоздалого ответа после reset. Нет сетевого таймаута, AbortSignal, runtime-валидации HTTP JSON, серверной сессии, стриминга и классификации ошибок. Старый запрос игнорируется, но физически не отменяется.

## Карта демо-зависимостей

| Место | Что делает сейчас | Что потребуется при интеграции |
|---|---|---|
| `agent/adapter.ts` | MockAgentAdapter, задержка 650 мс, processRequest, шаблонные ответы | HTTP-переводчик и runtime-проверка ответа, без fallback на мок при сетевой ошибке |
| `data/trips.ts` | 15 вымышленных поездок, отели, цены, визы, услуги | Предложения и подтверждённые сведения сервера |
| `agent/parser.ts` | Локальные словари, распознавание, фиксированная опорная дата, статусы, неизвестные пожелания | Согласовать владельца извлечения параметров и календарный контекст |
| `agent/blocker.ts` | Поиск разрешён при 3 известных слотах либо ровно when + origin; осмысленный Vague учитывается | Сохранить согласованный алгоритм; сервер возвращает решение и объяснение |
| `agent/ranking.ts` | Импорт каталога, отбор, цена, ранжирование | Серверные цены и порядок; формулу не переносить как реальную |
| `agent/conflicts.ts` | Импорт каталога; hard/soft конфликты и текстовые альтернативы; scheduleProblems — учебная проверка времени | Серверные конфликты, основания и допустимые действия |
| `state/useTravelSession.ts` | Вся Session в браузере; updateDetails и beginBookingEdit вызывают rankTrips/checkConflicts; book создаёт UUID и confirmed; cancelBooking локально ставит cancelled | Отдельные серверные операции пересчёта, оформления, изменения и отмены |
| `state/session.ts` | applyResponse локально меняет выбор и статус booking по changes и наличию ID в results | Не считать отсутствие в top-5 отменой реальной брони; сервер — владелец её статуса |
| `state/initial.ts`, `state/persistence.ts` | Начальные оценки гостей/ночей, localStorage v2, восстановление/миграция старой демо-сессии | Отдельное пространство хранения для API, сверка с сервером; демо-confirmed нельзя мигрировать в реальную бронь |
| `booking/review.ts` | Локальные origin-справочник, ограничения, формулы цены и блокировки оформления | Серверный quote/review с ошибками полей и актуальной доступностью |
| `components/Booking.tsx` | Прямо вызывает bookingBlockers; синхронный onBook, автоматические локальные правки; onCancel уже допускает Promise | Явные pending/error/success для асинхронного оформления и изменения; успех только после ответа сервера |
| `components/JourneyCard.tsx`, `TripCard.tsx` | scheduleProblems; выведенные причины, визы; путь /images/{image}.jpg; dateRange подставляет примерные даты | Валидированные серверные риски, медиа, даты и сегменты; значения не домысливать |
| `agent/itinerary.ts` | flightExample вычисляет рейсы, фиксированную пересадку в Стамбуле, обратную длительность; ограниченные зоны | Реальные сегменты с датами, UTC и IANA-зонами; простая замена каталога недостаточна |
| `booking/pdfData.ts`, `tripPdf.ts` | PDF из снимка демо-брони, расписание через flightExample, учебные советы | Точный подтверждённый сервером снимок; убрать синтез рейсов перед реальной продажей |
| `reminders/model.ts`, `calendar.ts`, `TripReminders.tsx` | Локальное расписание от flightExample, локальные настройки, статический .ics | Реальный маршрут; отдельно согласовать сервер уведомлений и статусы доставки |
| `components/Workspace.tsx` | Временное избранное/сортировка; повторная сортировка по score, UI-only перенос выбранной поездки; демо-тексты пустого состояния | Согласовать порядок сервера; тексты и возможности должны зависеть от режима |
| `src/compositions/main.tsx`, `src/break-card/main.tsx` | Отдельные демонстрационные/референсные страницы, MockAgentAdapter/processRequest или прямой каталог | Не являются интеграционным контуром; оставить изолированными |

`shared/format.ts` теперь содержит только форматирование рублей. Основные UI-компоненты больше не импортируют ranking только ради money. Старый экспорт money из ranking сохранён для совместимости. Прочие косвенные зависимости от каталога через проверки/booking остаются **намеренно отмеченными**, а не замаскированы переименованием.

Дизайн, согласованный Blocker и бизнес-правила не менялись. Демо-тексты, рейтинги, визы, бронирование и отмена сохранены до появления настоящего интеграционного режима.

## Данные, необходимые фронтенду

Минимальный внутренний контракт подробно задан в `src/types.ts`; сетевой контракт может отличаться, но адаптер обязан преобразовать его без потери смысла.

| Область | Необходимые данные |
|---|---|
| Диалог | Текст ответа; в предлагаемом сетевом расширении — sessionId, messageId, requestId, revision. Сейчас request содержит text, полные preferences, selectedId?, slotContext?; история не отправляется |
| Параметры | Все 4 slots: when/destination/origin/purpose; value и ровно YES/Vague/NO; rawValue?, resolution?, catalogSupport?. Указанное, но неподдержанное направление нельзя превращать в NO |
| Предпочтения | month?, startDate?, nights, nightsEstimated, guests, guestsEstimated, budget?, stars?, starsStrict, visaFree, visaStrict, passport?, pet, petStrict, seaOnly, poolAccepted, central, earlyCheckin, privateTransfer, purposes[], unknownPurposes?, pendingInput?, awaitingSlot? |
| Blocker | canSearch; предлагаемое расширение — missingSlots[], reason, allowedActions[]. Сейчас отдельного объекта blocker нет: уточнение находится в message/preferences |
| Конфликты | id, title, description, hard, alternatives[{label,message}]. Сейчас выбор альтернативы отправляет обычный текст, а не серверный action ID |
| Предложения | results[] от 0 до 5: trip, score, reasons[], compromises[], costs{transport,hotel,transfer,extras}, total. Стабильный trip.id, без индекса массива |
| Trip | id, country, city, region, destinationKeys[], airport, image, title, subtitle, hotel, purposes[], seasons[], warmSea[], heatedPool, central, visaForRU, visaNote, costs, flightHours, transferMinutes, stop, arrival, outbound, returnDeparture, activities[], risk |
| Hotel | name, stars, rating (сейчас строка), description, amenities[], meals, pets, checkin, checkinUntil, checkout |
| Пересборка | Полный обновлённый снимок preferences/results/conflicts и changes[]. Значения changes: when, destination, origin, purpose, budget, pet, stars, visa, passport, nights, guests, central, earlyCheckin, transfer, pendingInput. Последние earlyCheckin/transfer влияют на локальную логику сохранения демо-брони — нельзя молча переименовать |
| Оформление | Предлагаются quoteId/version, срок цены, currency, состав итоговой цены, доступность, blockers/errors полей, bookingId, статус операции, подтверждённый snapshot, правила отмены. Сейчас этих серверных сущностей нет |
| Реальный маршрут | Сегменты туда/обратно, перевозчики, аэропорты, номера рейсов, время начала/конца с UTC/offset и IANA-зонами, пересадки, багаж, трансферы, даты заезда/выезда. Не восстанавливать из строк flightHours/stop |

Сейчас стоимость — целое число рублей, гости — только 1–6 взрослых, ночи — 1–30 при восстановлении, паспорт RU/OTHER. Валюта не является полем. Новый API должен либо поддержать эти ограничения на первом этапе, либо потребует отдельного согласованного изменения типов/UI. Денежные значения, даты, enum, обязательные вложенные поля и URL медиа проверяются на границе; TypeScript `as AgentResponse` этого не делает.

## Предлагаемый JSON для чата (не существующий API)

Полный минимальный запрос с частичным намерением; никаких скрытых города или месяца:

```json
{
  "text": "Хочу горы и SPA",
  "preferences": {
    "slots": {
      "when": {"value": "", "status": "NO"},
      "destination": {"value": "", "status": "NO"},
      "origin": {"value": "", "status": "NO"},
      "purpose": {"value": "", "status": "NO"}
    },
    "nights": 6, "nightsEstimated": true, "guests": 1, "guestsEstimated": true,
    "starsStrict": false, "visaFree": false, "visaStrict": false,
    "pet": false, "petStrict": true, "seaOnly": false, "poolAccepted": false,
    "central": false, "earlyCheckin": false, "privateTransfer": false, "purposes": []
  }
}
```

Полный пример ответа внутреннего формата: сервер сохраняет известное и задаёт уточнение. При NO у происхождения/даты никаких выдуманных значений:

```json
{
  "message": "Из какого города начнём путешествие?",
  "preferences": {
    "slots": {
      "when": {"value": "", "status": "NO"},
      "destination": {"value": "", "status": "NO"},
      "origin": {"value": "", "status": "NO"},
      "purpose": {"value": "Горы, SPA", "status": "YES", "resolution": "resolved"}
    },
    "nights": 6, "nightsEstimated": true, "guests": 1, "guestsEstimated": true,
    "starsStrict": false, "visaFree": false, "visaStrict": false,
    "pet": false, "petStrict": true, "seaOnly": false, "poolAccepted": false,
    "central": false, "earlyCheckin": false, "privateTransfer": false,
    "purposes": ["mountains", "spa"], "awaitingSlot": "origin"
  },
  "canSearch": false, "results": [], "conflicts": [], "changes": ["purpose"]
}
```

Фрагмент альтернативы (включается в conflicts[], не является целым ответом):

```json
{"id":"budget-review","title":"Бюджет не покрывает обязательные условия","description":"Измените бюджет или явно согласуйте компромисс.","hard":true,"alternatives":[{"label":"Снять лимит бюджета","message":"Без лимита бюджета"}]}
```

Для найденных поездок results содержит полные объекты RankedTrip/Trip/Hotel по таблице выше; пустой массив означает отсутствие предложений, а не сетевую ошибку. reasons и compromises — реальные объяснения сервера, а не текст, генерируемый браузером ради заполнения карточки.

## Предлагаемое расширение для оформления (не реализовано)

Имена операций ниже условные; это не URL и не существующие методы AgentAdapter:

```json
{"operation":"reviewSelection","sessionId":"example-session","offerId":"example-offer","offerVersion":"example-version","startDate":"2027-06-12","guests":1,"origin":"Москва"}
```

```json
{"quoteId":"example-quote","version":"example-version","expiresAt":"2027-06-01T12:00:00Z","currency":"RUB","total":90000,"costs":{"transport":40000,"hotel":45000,"transfer":5000,"extras":0},"available":true,"blockers":[],"fieldErrors":{}}
```

```json
{"operation":"confirmBooking","quoteId":"example-quote","quoteVersion":"example-version","idempotencyKey":"unique-per-user-confirmation"}
```

```json
{"bookingId":"example-booking","status":"confirmed","confirmedAt":"2027-06-01T11:00:00Z","quoteId":"example-quote","version":"booking-version-1"}
```

Этот ответ оформления — только пример оболочки. Для работы PDF/карточки/напоминаний дополнительно обязателен подтверждённый snapshot предложения, предпочтений и реального маршрута. Его форму необходимо согласовать; нельзя преобразовать эту короткую оболочку в Session.booking без данных. Статусы pending/failed/cancelled и переходы требуется отдельно согласовать; текущий UI знает лишь демо confirmed/needs-confirmation/cancelled.

Отмена: условный запрос `{ "bookingId": "example-booking", "expectedVersion": "booking-version-1", "idempotencyKey": "unique-cancellation" }`; подтверждённый ответ `{ "bookingId": "example-booking", "status": "cancelled", "version": "booking-version-2" }`. Не показывать успех и не отключать серверные напоминания до подтверждения. Сбой оставляет прежнюю бронь. Изменение подтверждённой поездки должно быть отдельной согласованной операцией, а не локальной правкой снимка.

Предлагаемая ошибка, тоже не согласованный контракт:

```json
{"requestId":"example-request","error":{"code":"QUOTE_EXPIRED","message":"Цена устарела. Обновите расчёт.","retryable":false,"fieldErrors":{}}}
```

Согласовать 401/403, 409 для устаревшей версии, 422 для полей, 429, 5xx, офлайн и таймауты. Нельзя автоматически повторять оформление/отмену без идемпотентности. Чат сейчас сводит ошибки к одному понятному сообщению.

## Безопасность

В проверенных src, конфигурации Vite, корневых файлах и текущем dist нет обнаруженных ключей поставщиков, private keys или браузерной авторизации. Файлов .env в корне и frontend не найдено. `process.env` в QA-скриптах задаёт адрес/канал тестового браузера, не ключ приложения. Это статическая проверка текущих файлов, не аудит истории репозитория или инфраструктуры команды.

Vite /health — только проверка работоспособности фронтенда, не API агента. fetch в PDF загружает локальные шрифты. Реальных HTTP-запросов к агенту сейчас нет.

API-ключи LLM/туроператоров остаются на сервере. VITE_* публичны и попадают в браузер. Не хранить секреты в localStorage: сейчас там диалог, пожелания, снимок демо-брони и напоминания. При подключении согласовать пользовательскую авторизацию (например, серверная HttpOnly cookie), CORS/CSRF и очистку данных при выходе. Браузерный Session не является доказательством оплаты, цены или прав пользователя. Ответы агента выводятся как React-текст, не HTML.

## Порядок подключения и запрос команде

1. Получить OpenAPI/JSON Schema или реальные примеры ответов, адрес тестового окружения, авторизацию, CORS и владельца серверной сессии. Нужны примеры: уточнение, Vague, hard/soft конфликт, 0/1/5 поездок, пересборка, ошибка, изменение цены и отмена.
2. Зафиксировать контракт слотов и Blocker, changes, версии предложений и источники реальных маршрутов/виз/цен. Если сервер хранит контекст, добавить sessionId и revision; текущий stateless запрос не отправляет историю.
3. Реализовать HTTP AgentAdapter с runtime-валидацией, преобразованием DTO, таймаутом и отменой. Передать стабильный экземпляр в App. Не включать реальный режим только заменой адаптера: оставшиеся локальные правила могут пересчитать серверную цену по моковому каталогу.
4. Отдельно согласовать и реализовать review/confirm/change/cancel. Перевести updateDetails, beginBookingEdit, book/cancel, applyResponse и UI ожидания на серверный источник истины. Удалить демо-вычисления из реального пути PDF, карточек и напоминаний. Сохранить демо как отдельный явно выбранный режим, без молчаливого fallback.
5. Изолировать хранилище реального режима; не доверять восстановленному booked. Загрузить актуальную серверную бронь/сессию. Избранное остаётся временным, пока не согласовано иное.
6. Выполнить npm test, npm run build и браузерные сценарии с контрактными ответами команды: повторы, reset во время запроса, устаревшая цена, отказ бронирования/отмены, PDF из фактического маршрута. Не проверять настоящие платежи до отдельного согласования.

Пока готова заменяемая граница **чата**, но не полноценный production-контур покупки. Это сознательно зафиксированный результат подготовки, а не заявление о доступном API.
