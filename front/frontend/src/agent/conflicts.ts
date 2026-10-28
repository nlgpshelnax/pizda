import type { Conflict, Preferences, Trip } from '../types';
import { trips } from '../data/trips';
import { calculateCosts, destinationMatches, totalCosts } from './ranking';

export const minutes = (time: string) => { const [h, m] = time.split(':').map(Number); return h * 60 + m; };
export function scheduleProblems(trip: Trip): string[] {
  const problems: string[] = [];
  const hotelArrival = minutes(trip.arrival) + 60 + trip.transferMinutes;
  if (hotelArrival > minutes(trip.hotel.checkinUntil)) problems.push('Трансфер прибывает после закрытия регистрации: требуется согласовать поздний заезд.');
  const airportArrival = minutes(trip.hotel.checkout) + trip.transferMinutes;
  if (minutes(trip.returnDeparture) - airportArrival < 180) problems.push('До обратного вылета остаётся менее 3 часов: нужен более ранний трансфер.');
  return problems;
}
export function checkConflicts(p: Preferences, catalog: Trip[] = trips): Conflict[] {
  const conflicts: Conflict[] = [];
  const matches = catalog.filter(t => destinationMatches(t, p));
  if (p.slots.destination.catalogSupport === 'unsupported') conflicts.push({ id:'destination-coverage', title:'Направление сохранено, предложений пока нет', hard:false,
    description:`${p.slots.destination.value}: в локальном каталоге нет поездок по этому направлению. Это не означает, что направление не указано.`,
    alternatives:[{label:'Рассмотреть Европу',message:'В Европу'}, {label:'Любое направление',message:'Любое направление'}] });
  if (p.slots.origin.catalogSupport === 'unsupported') conflicts.push({ id:'origin-coverage', title:'Город отправления сохранён', hard:false,
    description:`Из ${p.slots.origin.value} в демо нет маршрутов. Без согласованного города нельзя обоснованно рассчитать дорогу.`,
    alternatives:[{label:'Вылет из Москвы',message:'Из Москвы'}, {label:'Из Санкт-Петербурга',message:'Из Санкт-Петербурга'}] });
  for (const wish of p.unknownPurposes ?? []) conflicts.push({ id:'purpose-coverage', title:wish.strict ? 'Обязательное занятие не подтверждено' : 'Пожелание сохранено отдельно', hard:wish.strict,
    description:`«${wish.value}»: ${wish.strict ? 'не заменяем это требование без согласия.' : wish.related?.length ? 'близкие варианты отмечены как альтернатива, само занятие не подтверждено.' : 'в каталоге нет подтверждения этого занятия. Уточните цель или разрешите другой тип отдыха.'}`,
    alternatives:[...(wish.related?.includes('beach') ? [{label:'Рассмотреть пляжный отдых',message:'Согласен на пляжный отдых вместо прежней цели'}] : []), {label:'Выбрать прогулки',message:'Вместо прежней цели хочу прогулки'}, {label:'Выбрать SPA',message:'Вместо прежней цели хочу SPA'}] });
  if (p.purposes.includes('beach') && p.month && [11, 12, 1, 2, 3].includes(p.month) && !p.poolAccepted) {
    conflicts.push({ id: 'winter-sea', title: 'Море может оказаться прохладнее, чем хочется',
      description: p.seaOnly ? 'Вы указали «только море». В учебном каталоге нет подтверждённого тёплого моря зимой в Европе. Требование сохранено: результаты появятся после согласованного изменения.' : 'Зимой европейское море обычно не подходит для комфортного купания. Варианты с бассейном ниже отмечены как компромисс, который нужно согласовать.', hard: p.seaOnly,
      alternatives: [
        { label: 'Согласен на бассейн', message: 'Согласен на подогреваемый бассейн вместо моря' },
        { label: 'Перенести на июль', message: 'Давай в июле, хочу купаться в море' },
        { label: 'Выбрать SPA', message: 'Вместо моря хочу SPA' },
        { label: 'Прогулки вместо купания', message: 'Вместо купания хочу прогулки и архитектуру' },
      ] });
  }
  if (p.stars && p.budget && matches.length) {
    const min = Math.min(...matches.filter(t => t.hotel.stars >= p.stars!).map(t => totalCosts(calculateCosts(t, p))));
    if (min > p.budget) conflicts.push({ id: 'stars-budget', title: 'Звёздность и бюджет пока не сходятся', hard: p.starsStrict,
      description: `В этом каталоге отель ${p.stars}★ с дорогой не укладывается в бюджет. ${p.starsStrict ? 'Условие «только» сохранено.' : 'Более доступные отели показаны с пометкой о компромиссе.'}`,
      alternatives: [
        { label: 'Рассмотреть 4★', message: 'Согласен на 4 звезды' },
        { label: 'Рассмотреть 3★', message: 'Согласен на 3 звезды' },
        { label: 'Сократить до 3 ночей', message: 'Сократить поездку до 3 ночей' },
        ...(Number.isFinite(min) ? [{ label: 'Увеличить бюджет', message: `Бюджет до ${min} рублей` }] : []),
      ] });
  }
  if (p.visaFree && p.passport !== 'RU') conflicts.push({ id: 'passport', title: 'Для визового условия нужен паспорт', hard: p.visaStrict,
    description: 'Гражданство не определено или отсутствует в демо-справочнике. Учебные визовые сценарии подготовлены только для паспорта РФ.',
    alternatives: [{ label: 'У меня паспорт РФ', message: 'У меня паспорт РФ' }, { label: 'Можно с визой', message: 'Можно с визой' }] });
  if (p.visaFree && p.visaStrict && p.passport === 'RU' && matches.length && matches.every(t => t.visaForRU === 'required')) conflicts.push({ id: 'visa', title: 'Направление конфликтует с условием «без визы»', hard: true,
    description: 'По учебному справочнику для выбранного направления нужна виза. Смените страну или разрешите визовый вариант. Актуальные правила не проверялись.',
    alternatives: [{ label: 'Рассмотреть Сербию', message: 'Вместо этого хочу в Сербию' }, { label: 'Рассмотреть Черногорию', message: 'Вместо этого хочу в Черногорию' }, { label: 'Можно с визой', message: 'Можно с визой' }] });
  if (p.pet && matches.length && matches.every(t => !t.hotel.pets)) conflicts.push({ id: 'pet', title: 'Питомец тоже едет, а отель его не принимает', hard: true,
    description: 'Отели этого направления в учебном каталоге не допускают животных. Не будем исключать питомца из поездки без вашего решения.',
    alternatives: [{ label: 'Другие направления', message: 'Любое направление, с нами едет собака' }, { label: 'Португалия', message: 'Давай в Португалию с собакой' }, { label: 'Сербия', message: 'Давай в Сербию с собакой' }] });
  return conflicts;
}
