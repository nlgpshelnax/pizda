import type { Preferences, RankedTrip } from '../types';
import { destinationZone, flightExample, originZone } from '../agent/itinerary';
import { scheduleProblems } from '../agent/conflicts';

export class PdfPlanError extends Error {}

const supportedOrigins = new Set(['Москва', 'Санкт-Петербург', 'Казань', 'Екатеринбург', 'Новосибирск', 'Сочи']);
const safe = (value?: string) => value?.trim() || 'Требует уточнения';
const day = (value: string) => {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? 'Требует уточнения' : new Intl.DateTimeFormat('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',timeZone:'UTC'}).format(date);
};
const localAdd = (date: string, time: string, minutes: number) => {
  const value = new Date(`${date}T${time}:00Z`);
  if (Number.isNaN(value.getTime())) return 'Требует уточнения';
  value.setUTCMinutes(value.getUTCMinutes() + minutes);
  return `${day(value.toISOString().slice(0,10))} ${value.toISOString().slice(11,16)}`;
};

export interface PdfPlanData {
  destination: string; origin: string; start: string; end: string; nights: number; guests: number; total: number;
  outbound: string[]; inbound: string[]; hotel: string[]; activities: string[];
  costs: { label: string; amount: number }[]; warnings: string[]; advice: string[];
}

/** Uses the confirmed booking snapshot. Never synthesises a date or an unknown origin. */
export function preparePdfPlan(r: RankedTrip, p: Preferences): PdfPlanData {
  if (!p.startDate || !/^\d{4}-\d{2}-\d{2}$/.test(p.startDate) || !Number.isFinite(p.nights) || !Number.isFinite(p.guests)) throw new PdfPlanError('Для PDF уточните дату и число путешественников, затем оформите поездку снова.');
  if (!r?.trip || !r.costs || !Number.isFinite(r.total)) throw new PdfPlanError('Не хватает сведений о выбранной поездке. Откройте её и попробуйте снова.');
  const t = r.trip;
  const start = p.startDate;
  const endValue = new Date(`${start}T12:00:00Z`);
  if (Number.isNaN(endValue.getTime())) throw new PdfPlanError('Уточните дату поездки перед созданием PDF.');
  endValue.setUTCDate(endValue.getUTCDate() + p.nights);
  const end = endValue.toISOString().slice(0,10);
  const origin = safe(p.slots?.origin?.value);
  const knownDestination = ['Италия','Франция','Сербия','Черногория','Венгрия','Австрия','Греция','Португалия','Испания'].includes(t.country);
  const exactRoute = supportedOrigins.has(origin) && knownDestination && !!t.arrival && !!t.returnDeparture && !!t.flightHours && !!t.stop;
  const f = exactRoute ? flightExample(t,p,start,end) : null;
  const connection = !!t.stop && t.stop !== 'Без пересадок';
  const airport = t.airport && t.airport !== 'XXX' ? t.airport : 'аэропорт уточняется';
  const transfer = Number.isFinite(t.transferMinutes) ? `${t.transferMinutes} мин` : 'время уточняется';
  const toHotel = exactRoute && Number.isFinite(t.transferMinutes) ? localAdd(start,t.arrival,60+t.transferMinutes) : 'Время уточняется';
  const afterArrival = exactRoute ? localAdd(start,t.arrival,60) : 'Время уточняется';
  const checkin = safe(t.hotel?.checkin);
  const checkout = safe(t.hotel?.checkout);
  let expectedCheckin = 'время уточняется';
  if (exactRoute && Number.isFinite(t.transferMinutes) && /^\d{2}:\d{2}$/.test(checkin)) {
    const arrivalAtHotel = new Date(`${start}T${t.arrival}:00Z`);
    arrivalAtHotel.setUTCMinutes(arrivalAtHotel.getUTCMinutes()+60+t.transferMinutes);
    const opening = new Date(`${arrivalAtHotel.toISOString().slice(0,10)}T${checkin}:00Z`);
    const checkinAt = new Date(Math.max(arrivalAtHotel.getTime(),opening.getTime()));
    expectedCheckin = `${day(checkinAt.toISOString().slice(0,10))} ${checkinAt.toISOString().slice(11,16)}`;
  }
  const outbound = [
    `${origin} → ${safe(t.city)} · ${f ? `${day(f.departure.date)} ${f.departure.time} (${originZone(p)})` : 'отправление уточняется'}`,
    !t.stop ? 'Пересадки: требуют уточнения' : connection ? `Пересадка: ${safe(t.stop)}${f && t.stop==='Стамбул' ? ` · ${day(f.connectionArrival.date)} ${f.connectionArrival.time}–${f.connectionDeparture.time} (Europe/Istanbul)` : ' · время уточняется'}` : 'Без пересадок',
    `Прибытие ${airport}: ${f ? `${day(f.arrival.date)} ${f.arrival.time} (${destinationZone(t)})` : 'время уточняется'}`,
    `Трансфер ${p.privateTransfer ? 'индивидуальный' : 'групповой'}: ${afterArrival}, ${transfer}; прибытие в отель ${toHotel}.`,
    `Заселение примерно ${expectedCheckin}; регистрация с ${checkin}${p.earlyCheckin ? '; ранний заезд запрошен, не подтверждён' : ''}.`,
  ];
  const inbound = [
    `Выезд из отеля: ${day(end)}, до ${checkout}; трансфер ${transfer}.`,
    `Обратный вылет ${airport}: ${t.returnDeparture && knownDestination ? `${day(end)} ${t.returnDeparture} (${destinationZone(t)})` : 'время уточняется'}.`,
    'Обратные пересадки: требуют уточнения.',
    `Прибытие в ${origin}: ${f ? `${day(f.returnArrival.date)} ${f.returnArrival.time} (${originZone(p)})` : 'время уточняется'}.`,
  ];
  const visa = p.passport !== 'RU' ? 'Гражданство не указано или не подтверждено. Визовые условия уточнить.' : t.visaForRU === 'free' ? 'По учебным данным для паспорта РФ виза не требуется. Правила въезда уточнить.' : t.visaForRU === 'required' ? 'По учебным данным для паспорта РФ нужна виза. Правила въезда уточнить.' : 'Визовые условия для паспорта РФ требуют уточнения.';
  const routeComplete = !!t.hotel && !!t.arrival && !!t.returnDeparture && !!t.hotel.checkinUntil && !!t.hotel.checkout && Number.isFinite(t.transferMinutes);
  const warnings = [visa, ...(r.compromises ?? []).map(safe), ...(t.risk ? [t.risk] : []), ...(routeComplete ? scheduleProblems(t) : [])];
  return {
    destination: `${safe(t.city)}, ${safe(t.country)}`, origin, start, end, nights:p.nights, guests:p.guests, total:r.total,
    outbound, inbound,
    hotel: [`${safe(t.hotel?.name)} · ${Number.isFinite(t.hotel?.stars) ? `${t.hotel.stars} зв.` : 'категория уточняется'}`, `${safe(t.city)} · адрес не указан`, `${day(start)} – ${day(end)} · ${p.nights} ночей`, `Питание: ${safe(t.hotel?.meals)}`, ...(p.pet ? [`Питомец: ${t.hotel?.pets ? 'размещение допускается; условия уточнить' : 'размещение требует уточнения'}`] : [])],
    activities: (t.activities ?? []).filter(Boolean),
    costs: [ {label:'Перелёт / дорога',amount:r.costs.transport}, {label:'Проживание',amount:r.costs.hotel}, {label:'Трансферы',amount:r.costs.transfer}, {label:'Дополнительные расходы',amount:r.costs.extras} ],
    warnings,
    advice: ['Уточните правила багажа и заселения.', ...(connection ? ['Проверьте условия и документы для пересадки.'] : []), ...(p.pet ? ['Проверьте документы и правила перевозки питомца.'] : [])],
  };
}
