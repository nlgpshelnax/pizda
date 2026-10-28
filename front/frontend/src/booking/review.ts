import type { Preferences, RankedTrip } from '../types';
import { calculateCosts, destinationMatches, totalCosts } from '../agent/ranking';
import { checkConflicts, scheduleProblems } from '../agent/conflicts';
import { flightExample } from '../agent/itinerary';

export const supportedOrigins = ['Москва', 'Санкт-Петербург', 'Казань', 'Екатеринбург', 'Новосибирск', 'Сочи'];
export interface BookingFields { date: string; guests: string; origin: string }
export type BookingFieldErrors = Partial<Record<keyof BookingFields, string>>;
export type BookingDetailsPatch = Partial<Pick<Preferences, 'startDate' | 'month' | 'guests' | 'guestsEstimated'>> & { origin?: string };
export function todayInMoscow(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Moscow', year:'numeric', month:'2-digit', day:'2-digit'}).format(now);
}
export function validateBookingFields(fields: BookingFields, now = new Date()): BookingFieldErrors {
  const errors: BookingFieldErrors = {};
  const parsed = new Date(`${fields.date}T12:00:00Z`);
  if (!fields.date || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0,10) !== fields.date) errors.date = 'Выберите корректную дату.';
  else if (fields.date < todayInMoscow(now)) errors.date = 'Дата поездки уже прошла.';
  if (!/^\d+$/.test(fields.guests) || Number(fields.guests) < 1 || Number(fields.guests) > 6) errors.guests = 'Укажите от 1 до 6 взрослых.';
  if (!fields.origin.trim()) errors.origin = 'Укажите город отправления.';
  else if (!supportedOrigins.includes(fields.origin.trim())) errors.origin = 'Город сохранён. В демо нет расчёта транспорта из этого города.';
  return errors;
}
export function patchBookingPreferences(previous: Preferences, patch: BookingDetailsPatch): Preferences {
  const { origin, ...details } = patch;
  const p = { ...previous, ...details, slots: { ...previous.slots } };
  if (details.startDate) {
    const date = new Date(`${details.startDate}T12:00:00Z`);
    p.month = date.getUTCMonth() + 1;
    p.slots.when = { value: date.toLocaleDateString('ru-RU', {day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}), status:'YES' };
  }
  if (origin !== undefined) p.slots.origin = { value: origin.trim(), status:origin.trim() ? 'YES' : 'NO', rawValue:origin.trim(), resolution:supportedOrigins.includes(origin.trim()) ? 'resolved' : 'unresolved', catalogSupport:supportedOrigins.includes(origin.trim()) ? 'supported' : 'unsupported' };
  if ((origin !== undefined && p.awaitingSlot === 'origin') || (details.startDate && p.awaitingSlot === 'when')) p.awaitingSlot = undefined;
  return p;
}
export function recalculateBooking(result: RankedTrip, preferences: Preferences): RankedTrip {
  const costs = calculateCosts(result.trip, preferences);
  return { ...result, costs, total: totalCosts(costs) };
}
export function bookingBlockers(result: RankedTrip, p: Preferences, now = new Date()): string[] {
  const fields = {date:p.startDate ?? '',guests:String(p.guests),origin:p.slots.origin.value};
  const messages = Object.values(validateBookingFields(fields, now));
  if (!destinationMatches(result.trip,p)) messages.push('Выбранный отель не соответствует новому направлению. Выберите другую поездку.');
  if (p.budget && result.total > p.budget) messages.push('Стоимость превышает ваш бюджет. Измените гостей или бюджет в диалоге.');
  if (p.pet && !result.trip.hotel.pets) messages.push('Этот отель не принимает питомцев.');
  if (p.starsStrict && p.stars && result.trip.hotel.stars < p.stars) messages.push('Отель не соответствует обязательной звёздности.');
  if (p.seaOnly && p.purposes.includes('beach') && (!p.month || !result.trip.warmSea.includes(p.month))) messages.push('Поездка не подтверждает обязательное купание в тёплом море.');
  for (const conflict of checkConflicts(p)) if (conflict.hard) messages.push(conflict.title);
  messages.push(...scheduleProblems(result.trip));
  if (!messages.length && p.startDate) {
    const end = new Date(`${p.startDate}T12:00:00Z`); end.setUTCDate(end.getUTCDate() + p.nights);
    if (flightExample(result.trip,p,p.startDate,end.toISOString().slice(0,10)).departureInstant.getTime() <= now.getTime()) messages.push('Время отправления уже прошло. Выберите другую дату.');
  }
  return [...new Set(messages)];
}
