import type { Preferences, Purpose, Slot, SlotKey, SlotStatus } from '../types';

export const monthNames = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const monthPatterns = [/январ/, /феврал/, /март/, /апрел/, /ма[йяе](?:\s|$|[,.])/, /июн/, /июл/, /август/, /сентябр/, /октябр/, /ноябр/, /декабр/];
const cities: [RegExp, string][] = [
  [/москв|\bmsk\b/, 'Москва'], [/питер|петербург|спб/, 'Санкт-Петербург'], [/казан/, 'Казань'],
  [/екатеринбург|екб/, 'Екатеринбург'], [/новосибирск/, 'Новосибирск'], [/сочи/, 'Сочи'],
];
const destinations: [RegExp, string][] = [
  [/барселон/, 'Барселона'], [/тенериф|канар/, 'Тенерифе'], [/мадейр|мадер|фуншал/, 'Мадейра'],
  [/лиссабон/, 'Лиссабон'], [/париж/, 'Париж'], [/флоренц/, 'Флоренция'], [/\bрим\b|рима|риме/, 'Рим'],
  [/ницц/, 'Ницца'], [/белград/, 'Белград'], [/нови[ -]сад/, 'Нови-Сад'], [/копаоник/, 'Копаоник'],
  [/будапешт/, 'Будапешт'], [/инсбрук|альп/, 'Альпы'], [/котор/, 'Котор'], [/крит/, 'Крит'],
  [/испани/, 'Испания'], [/итали/, 'Италия'], [/португали/, 'Португалия'], [/франци/, 'Франция'],
  [/серби/, 'Сербия'], [/черногор/, 'Черногория'], [/венгри/, 'Венгрия'], [/австри/, 'Австрия'], [/грец/, 'Греция'],
  [/европ/, 'Европа'],
];
const purposePatterns: [RegExp, Purpose, string][] = [
  [/купат|плават|море|моря|пляж|загорат/, 'beach', 'Море и пляжи'],
  [/архитектур|музе|экскурс|искусств|достопримечательн|культур/, 'culture', 'Архитектура и музеи'],
  [/гор[ыаух]|горнолыж|лыж|сноуборд|снег/, 'mountains', 'Горы и природа'],
  [/\bspa\b|(?:^|[^а-яa-z])спа(?=$|[^а-яa-z])|бассейн|термальн/, 'spa', 'SPA и отдых'],
  [/прогул|гуля|пешком|гастроном|кафе/, 'walks', 'Прогулки и гастрономия'],
];
export interface ParseResult { preferences: Preferences; changes: string[]; recognized: boolean; unsupported?: string }

const normalizedText = (value: string) => value.toLowerCase().replace(/ё/g, 'е');
const cleanValue = (value: string) => value.trim().replace(/^[«"']|[»"']$/g, '').replace(/^(?:город(?:а)?|стран(?:а|у))\s+/i, '').trim();
const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
function placeMeaning(raw: string, role: 'origin' | 'destination'): Slot {
  const value = cleanValue(raw);
  const t = normalizedText(value);
  const origin = cities.find(([pattern]) => pattern.test(t));
  const destination = destinations.find(([pattern]) => pattern.test(t));
  const canonical = role === 'origin' ? origin?.[1] ?? destination?.[1] : destination?.[1] ?? origin?.[1];
  return { value: canonical ?? titleCase(value), rawValue: value,
    status: canonical === 'Европа' ? 'Vague' : 'YES',
    resolution: canonical ? 'resolved' : 'unresolved',
    catalogSupport: (role === 'origin' ? !!origin : !!destination) ? 'supported' : 'unsupported' };
}
function placeCandidates(text: string): { role: 'origin' | 'destination'; raw: string }[] {
  const candidates: { role: 'origin' | 'destination'; raw: string }[] = [];
  const pattern = /(?:^|[\s,;])(?<prep>из|в|во|на)\s+(?<place>[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\s.'’-]*?)(?=\s+(?:из|в|во|на|хочу|хотим|нужен|нужна|нужно|будем|купаться|плавать|гулять|посмотреть|заняться|с\s+собакой|для|бюджет|до|только|желательно|с\s+питомцем)(?:\s|$)|[,;!?]|$)/gi;
  for (const match of text.matchAll(pattern)) {
    const prep = normalizedText(match.groups?.prep ?? '');
    const raw = cleanValue(match.groups?.place ?? '');
    const t = normalizedText(raw);
    if (!raw || monthPatterns.some(p => p.test(t)) || purposePatterns.some(([pattern]) => pattern.test(t)) || /^(?:летом|зимой|весной|осенью|отпуск|море|моря|пляж|бассейн|недел|день|дня|дней|ноч|центр|центре|отель|гостиниц|эконом|двои|двое|два\s|две\s|три\s|четыре\s|пять\s|шесть\s|семь\s|память|компромисс|подогреваем|связи|перв|таком|этом)/.test(t)) continue;
    candidates.push({ role: prep === 'из' ? 'origin' : 'destination', raw });
  }
  const labelled = text.match(/(?:город\s+отправления|откуда|направление|город\s+назначения)\s*[:—-]\s*([^,;!?]+)/i);
  if (labelled) candidates.push({ role: /отправления|откуда/i.test(labelled[0]) ? 'origin' : 'destination', raw: cleanValue(labelled[1]) });
  return candidates;
}
const purposefulButUncatalogued: { pattern: RegExp; related?: Purpose[] }[] = [
  { pattern: /дайвинг|подводн.*погруж|нырять/, related: ['beach'] },
  { pattern: /серфинг|сёрфинг|серфить/, related: ['beach'] },
  { pattern: /снорклинг|сноркелинг/, related: ['beach'] },
  { pattern: /наблюда.*звезд|астроном|фотосафари|волонтер|волонтёр/ },
];

export function parseMessage(text: string, previous: Preferences, selectedTotal?: number, slotContext?: SlotKey): ParseResult {
  const p = structuredClone(previous);
  const t = text.toLowerCase().replace(/ё/g, 'е');
  const changes: string[] = [];
  const context = slotContext ?? previous.awaitingSlot;
  const set = (key: SlotKey, value: string, status: SlotStatus = 'YES', metadata: Partial<Slot> = {}) => {
    p.slots[key] = { value, status, ...metadata }; changes.push(key);
    if (p.awaitingSlot === key) delete p.awaitingSlot;
  };
  const monthIndex = monthPatterns.findIndex(pattern => pattern.test(t));
  const isoDate = t.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
  if (monthIndex >= 0) {
    p.month = monthIndex + 1;
    p.startDate = undefined;
    set('when', monthNames[monthIndex][0].toUpperCase() + monthNames[monthIndex].slice(1));
    const dayRange = t.match(/(?:с\s+)?(\d{1,2})\s*(?:[–—-]|по)\s*(\d{1,2})\s+[а-я]+/);
    const dayOnly = t.match(/(?:с\s+)?(\d{1,2})\s+(?:январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)/);
    const day = Number(dayRange?.[1] ?? dayOnly?.[1]);
    if (day) {
      const suppliedYear = t.match(/\b(20\d{2})\b/);
      const year = suppliedYear ? Number(suppliedYear[1]) : (p.month < 10 ? 2027 : 2026);
      const date = new Date(Date.UTC(year, p.month - 1, day));
      if (date.getUTCMonth() === p.month - 1 && date.getUTCDate() === day) {
        p.startDate = date.toISOString().slice(0, 10);
        set('when', date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }));
        if (dayRange && Number(dayRange[2]) > day) {
          p.nights = Number(dayRange[2]) - day; p.nightsEstimated = false; changes.push('nights');
        }
      }
    }
  } else if (/летом|летн/.test(t)) { p.month = 7; p.startDate = undefined; set('when', 'Лето', 'Vague'); }
  else if (/зимой|зимн|зимою/.test(t)) { p.month = 12; p.startDate = undefined; set('when', 'Зима', 'Vague'); }
  else if (/весной|весен/.test(t)) { p.month = 4; p.startDate = undefined; set('when', 'Весна', 'Vague'); }
  else if (/осенью|осенн/.test(t)) { p.month = 10; p.startDate = undefined; set('when', 'Осень', 'Vague'); }
  if (isoDate) {
    const date = new Date(`${isoDate[1]}T12:00:00Z`);
    if (Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === isoDate[1]) {
      p.startDate = isoDate[1]; p.month = date.getUTCMonth() + 1;
      set('when', date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }));
    }
  }
  if (/позже|раньше/.test(t) && /дн|день|дня/.test(t)) {
    const amount = Number(t.match(/на\s+(\d+)/)?.[1] ?? (/два|две/.test(t) ? 2 : /три/.test(t) ? 3 : /один/.test(t) ? 1 : 0));
    if (amount && p.startDate) {
      const d = new Date(`${p.startDate}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + amount * (/раньше/.test(t) ? -1 : 1));
      p.startDate = d.toISOString().slice(0, 10); p.month = d.getUTCMonth() + 1;
      set('when', d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }));
    } else return { preferences: p, changes, recognized: changes.length > 0, unsupported: 'Чтобы сдвинуть поездку, сначала укажите точную дату: например, «12 декабря».' };
  }
  const places = placeCandidates(text);
  if (context === 'origin' || context === 'destination') {
    const bare = cleanValue(text);
    if (!places.length && /^[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z .’'-]{1,65}$/.test(bare) &&
        !/хочу|бюджет|дешев|звезд|спасибо|привет|паспорт|питом|собак/.test(t) && !monthPatterns.some(pattern => pattern.test(t))) places.push({ role:context, raw:bare });
  }
  if (p.pendingInput && /^(?:(?:это|мой|мое)\s+)?(?:город\s+)?(?:отправлени[ея]|откуда|назначени[ея]|направление|куда)[.!]?$/i.test(text.trim())) {
    places.push({ role: /отправлен|откуда/i.test(t) ? 'origin' : 'destination', raw:p.pendingInput });
  }
  for (const { role, raw } of places) {
    const slot = placeMeaning(raw, role);
    set(role, slot.value, slot.status, slot); delete p.pendingInput;
  }
  // A known country may be named without a preposition. A bare city still needs a role.
  if (!places.length && !context) {
    const region = destinations.slice(15).find(([pattern]) => pattern.test(t));
    if (region && /^(?:хочу\s+)?[А-Яа-яЁё -]+[.!]?$/.test(text.trim())) {
      const slot = placeMeaning(region[1], 'destination'); set('destination', slot.value, slot.status, slot);
    }
  }
  if (/любое направление|куда угодно|сбрось направление/.test(t)) set('destination', '', 'NO');
  const purposeText = t.replace(/вместо\s+(?:моря|купани[яе]|пляжа)/g, '').replace(/не\s+хочу\s+(?:море|купаться)/g, '');
  const purposes = purposePatterns.filter(([pattern]) => pattern.test(purposeText));
  if (purposes.length) {
    const seaOnlyBefore = p.seaOnly;
    p.purposes = purposes.map(([, purpose]) => purpose);
    p.poolAccepted = false;
    p.seaOnly = false;
    delete p.unknownPurposes;
    set('purpose', purposes.map(([, , label]) => label).join(', '), 'YES', {rawValue:text.trim(),resolution:'resolved',catalogSupport:'supported'});
    if (purposes.some(([, purpose]) => purpose === 'beach')) {
      p.seaOnly = seaOnlyBefore || /только\s+(?:теплое\s+)?море|только\s+в\s+море|бассейн\s+не\s+подходит|исключительно\s+море/.test(t);
      p.poolAccepted = false;
    }
  }
  if (/согласен.*бассейн|согласна.*бассейн|подойдет.*бассейн|согласен на компромисс/.test(t)) {
    p.poolAccepted = true; p.seaOnly = false;
    p.purposes = ['beach', 'spa']; set('purpose', 'Море и подогреваемый бассейн');
    delete p.unknownPurposes;
  }
  const unsupportedActivity = purposefulButUncatalogued.find(item => item.pattern.test(purposeText));
  const explicitGoal = text.match(/(?:хочу|хотим|цель(?:\s+поездки)?\s*[:—-]?)\s+((?:заняться|заниматься|попробовать|наблюдать|посвятить|исследовать|посмотреть|увидеть)\s+[^,;.!?]+)/i);
  const plainGoal = !purposes.length && !/не\s+хочу/.test(t) ? text.match(/(?:хочу|хотим)\s+(?!в\s|во\s|на\s|из\s|отдохнуть|поехать|путешествовать|дешев|подешевле|сэконом|без\s|отель|гостиниц|снизить|сократить|перенести|изменить|оформить|собак|кошк|питом|[0-9])([^,;.!?]+)/i) : undefined;
  const rawGoal = explicitGoal?.[1]?.trim() ?? plainGoal?.[1]?.trim() ?? (context === 'purpose' && !places.length && !monthPatterns.some(pattern => pattern.test(t)) && !/бюджет|питом|собак|паспорт|звезд/.test(t) ? text.trim() : undefined);
  if (unsupportedActivity || (rawGoal && !purposes.length && !/отдохнуть|отдых|путешествие|поехать|сэконом|дешев|бюджет|виз|звезд|гост|взросл|трансфер/.test(normalizedText(rawGoal)))) {
    const value = rawGoal ?? text.trim();
    p.unknownPurposes = [{ value, strict: /только|обязательно|исключительно|строго/.test(normalizedText(value)), related:unsupportedActivity?.related }];
    if (!purposes.length) p.purposes = [];
    set('purpose', purposes.length ? `${purposes.map(([, , label]) => label).join(', ')}; ${value}` : titleCase(value), 'YES',
      {rawValue:text.trim(),resolution:unsupportedActivity ? 'resolved' : 'unresolved',catalogSupport:'unsupported'});
  }
  const budget = t.match(/(?:бюджет(?:ом|а)?|до|не более|максимум|за)\s*(\d[\d\s]*(?:[.,]\d+)?)\s*(тыс(?:яч)?\.?|т\.?\b|к\b|₽|руб)/)
    ?? t.match(/(\d[\d\s]*)\s*(тыс(?:яч)?\.?|₽|руб)/);
  if (budget) {
    const value = Number(budget[1].replace(/\s/g, '').replace(',', '.')) * (/тыс|^т|^к/.test(budget[2]) ? 1000 : 1);
    if (value >= 1000) { p.budget = value; changes.push('budget'); }
  }
  if (/подешевле|сэконом|снизь бюджет|дешевле/.test(t) && !budget) {
    p.budget = Math.round((p.budget ?? selectedTotal ?? 110000) * .8 / 1000) * 1000; changes.push('budget');
  }
  if (/без ограничений.*бюджет|без лимита|снять.*бюджет/.test(t)) { p.budget = undefined; changes.push('budget'); }
  const stars = t.match(/([3-5])\s*(?:★|\*|звезд)/);
  const wordStars = /вместо.*пят.*четыр|четыр[еех].*звезд/.test(t) ? 4 : /пят[ьи].*звезд/.test(t) ? 5 : /тр[ие].*звезд/.test(t) ? 3 : undefined;
  const starNumber = stars ? Number(stars[1]) : wordStars;
  if (starNumber) {
    p.stars = starNumber;
    p.starsStrict = /(?:только|обязательно|исключительно|строго)\s+(?:отель\s+|гостиница\s+)?(?:[3-5]\s*(?:★|\*|звезд)|пят|четыр|тр[еи])/.test(t);
    changes.push('stars');
  }
  if (/без виз|безвиз|не хочу.*виз/.test(t)) {
    p.visaFree = true; p.visaStrict = /(?:только|обязательно|строго)\s+без\s+виз/.test(t) || !/(?:желательно|по возможности)\s+(?:путешествие\s+)?без\s*виз/.test(t); changes.push('visa');
  } else if (/виза есть|есть.*шенген|готов.*виз|можно с визой/.test(t)) {
    p.visaFree = false; p.visaStrict = false; changes.push('visa');
  }
  if (/паспорт.*(?:рф|росси)|граждан(?:ин|ка|ство).*росси|я из россии/.test(t)) { p.passport = 'RU'; changes.push('passport'); }
  if (/другой паспорт|паспорт.*(?:сша|германи|франци)|другое гражданство/.test(t)) { p.passport = 'OTHER'; changes.push('passport'); }
  if (/собак|кошк|питом|животн/.test(t)) {
    p.pet = !/без\s+(?:собак|кошк|питом|животн)|не едет.*(?:собак|питом)/.test(t);
    p.petStrict = true; changes.push('pet');
  }
  if (/ближе к центру|в центре|центр города/.test(t)) { p.central = true; changes.push('central'); }
  const nights = t.match(/(?:на\s+)?(\d{1,2})\s*(?:ноч|дней|дня|день)/);
  if (nights && !/позже|раньше/.test(t) && !/(?:часа|часов)\s+до/.test(t) && !p.startDate?.includes(nights[0])) {
    const n = Number(nights[1]);
    if (n >= 1 && n <= 30) { p.nights = n; p.nightsEstimated = false; changes.push('nights'); }
  }
  if (/на неделю/.test(t)) { p.nights = 7; p.nightsEstimated = false; changes.push('nights'); }
  const guests = t.match(/([1-6])\s*(?:взросл|гост|человек|путешественник)/);
  if (guests || /вдвоем|на двоих|нас двое|еду один|еду одна|1 взрослый/.test(t)) {
    p.guests = guests ? Number(guests[1]) : /вдвоем|двоих|двое/.test(t) ? 2 : 1;
    p.guestsEstimated = false; changes.push('guests');
  }
  if (/ранний заезд|раннее заселение/.test(t)) { p.earlyCheckin = true; changes.push('earlyCheckin'); }
  if (/индивидуальный трансфер/.test(t)) { p.privateTransfer = true; changes.push('transfer'); }
  if (/обычный трансфер|групповой трансфер/.test(t)) { p.privateTransfer = false; changes.push('transfer'); }
  if (!changes.length && !context && /^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z'’.-]*(?:\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z'’.-]*){0,2}$/.test(text.trim()) && !/^(?:Привет|Спасибо|Здравствуйте|Хорошо|Да|Нет)$/i.test(text.trim())) {
    p.pendingInput = text.trim(); changes.push('pendingInput');
  }
  const recognized = changes.length > 0;
  return { preferences: p, changes: [...new Set(changes)], recognized };
}
