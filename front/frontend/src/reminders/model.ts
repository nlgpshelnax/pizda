import type { Preferences, RankedTrip } from '../types';
import { flightExample, originZone } from '../agent/itinerary';

/** Internal browser-only contract. A future notification adapter can consume this schedule. */
export type ReminderOffset = '7d' | '1d' | '3h';
export interface ScheduledReminder { offset: ReminderOffset; at: string }
export interface ReminderSettings {
  enabled: boolean;
  offsets: ReminderOffset[];
  schedule: ScheduledReminder[];
  routeKey: string;
  savedAt: string;
}
export interface ReminderBooking {
  id: string;
  confirmedAt: string;
  result: RankedTrip;
  preferences: Preferences;
}
export interface TripSchedule {
  departureAt: string;
  returnAt: string;
  startDate: string;
  endDate: string;
  timeZone: string;
  routeKey: string;
}
export interface ReminderState {
  upcoming: ScheduledReminder[];
  due: ScheduledReminder[];
  next?: ScheduledReminder;
  departed: boolean;
  available: boolean;
}
export const reminderOptions: { offset: ReminderOffset; label: string; milliseconds: number; trigger: string }[] = [
  { offset: '7d', label: 'За 7 дней', milliseconds: 7 * 24 * 60 * 60 * 1000, trigger: '-P7D' },
  { offset: '1d', label: 'За 1 день', milliseconds: 24 * 60 * 60 * 1000, trigger: '-P1D' },
  { offset: '3h', label: 'За 3 часа', milliseconds: 3 * 60 * 60 * 1000, trigger: '-PT3H' },
];
const originsWithKnownTimeZone = new Set(['Москва', 'Санкт-Петербург', 'Казань', 'Екатеринбург', 'Новосибирск', 'Сочи']);
const validInstant = (value: string) => Number.isFinite(Date.parse(value));
const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value)
  && validInstant(`${value}T12:00:00Z`)
  && new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) === value;

export function initialReminderSettings(): ReminderSettings {
  return { enabled: false, offsets: ['1d'], schedule: [], routeKey: '', savedAt: '' };
}
export function reminderUnavailableReason(booking: ReminderBooking): string | undefined {
  const p = booking.preferences;
  if (!p.startDate || !validDate(p.startDate)) return 'Сначала подтвердите точную дату поездки.';
  if (!originsWithKnownTimeZone.has(p.slots.origin.value)) return 'Для этого города отправления пока неизвестен часовой пояс. Напоминания и календарь станут доступны после уточнения маршрута.';
  if (!Number.isInteger(p.nights) || p.nights < 1 || p.nights > 365) return 'Нужно уточнить длительность поездки.';
  return undefined;
}
export function getTripSchedule(booking: ReminderBooking): TripSchedule | null {
  if (reminderUnavailableReason(booking)) return null;
  const startDate = booking.preferences.startDate!;
  const end = new Date(`${startDate}T12:00:00Z`);
  end.setUTCDate(end.getUTCDate() + booking.preferences.nights);
  const endDate = end.toISOString().slice(0, 10);
  try {
    const flight = flightExample(booking.result.trip, booking.preferences, startDate, endDate);
    if (![flight.departureInstant.getTime(), flight.returnArrivalInstant.getTime()].every(Number.isFinite)
      || flight.returnArrivalInstant <= flight.departureInstant) return null;
    const departureAt = flight.departureInstant.toISOString();
    const returnAt = flight.returnArrivalInstant.toISOString();
    return {
      departureAt, returnAt, startDate, endDate, timeZone: originZone(booking.preferences),
      routeKey: [booking.id, booking.result.trip.id, booking.preferences.slots.origin.value, departureAt, returnAt].join('|'),
    };
  } catch { return null; }
}
function uniqueOffsets(offsets: readonly ReminderOffset[]): ReminderOffset[] {
  return reminderOptions.filter(o => offsets.includes(o.offset)).map(o => o.offset);
}
export function reminderTime(booking: ReminderBooking, offset: ReminderOffset): string | undefined {
  const route = getTripSchedule(booking);
  const option = reminderOptions.find(o => o.offset === offset);
  if (!route || !option) return undefined;
  return new Date(Date.parse(route.departureAt) - option.milliseconds).toISOString();
}
/** Only future times enter a newly saved schedule. Exact-now triggers are already elapsed. */
export function saveReminderSettings(booking: ReminderBooking, enabled: boolean, offsets: readonly ReminderOffset[], now = new Date()): ReminderSettings {
  const route = getTripSchedule(booking);
  const chosen = uniqueOffsets(offsets);
  const schedule = enabled && route ? chosen.flatMap(offset => {
    const at = reminderTime(booking, offset);
    return at && Date.parse(at) > now.getTime() ? [{ offset, at }] : [];
  }) : [];
  return { enabled: enabled && !!route && schedule.length > 0, offsets: chosen, schedule, routeKey: route?.routeKey ?? '', savedAt: now.toISOString() };
}
/** Call when booking status/route changes; do not recreate unchanged schedules on every clock tick. */
export function reconcileReminderSettings(booking: ReminderBooking | undefined, settings: ReminderSettings, active: boolean, now = new Date()): ReminderSettings {
  if (!booking || !active) {
    if (!settings.enabled && settings.schedule.length === 0) return settings;
    return { ...settings, enabled: false, schedule: [], savedAt: now.toISOString() };
  }
  const route = getTripSchedule(booking);
  if (!route) return { ...settings, enabled: false, schedule: [], routeKey: '', savedAt: now.toISOString() };
  if (route.routeKey === settings.routeKey) return settings;
  return saveReminderSettings(booking, settings.enabled, settings.offsets, now);
}
/** Due means its saved time has arrived; this never asserts that anything was delivered. */
export function getReminderState(booking: ReminderBooking, settings: ReminderSettings, now = new Date()): ReminderState {
  const route = getTripSchedule(booking);
  const departed = !!route && Date.parse(route.departureAt) <= now.getTime();
  const available = !!route && settings.routeKey === route.routeKey && settings.enabled && !departed;
  const schedule = available ? settings.schedule.filter(item => validInstant(item.at)) : [];
  const upcoming = schedule.filter(item => Date.parse(item.at) > now.getTime()).sort((a,b) => Date.parse(a.at) - Date.parse(b.at));
  const due = schedule.filter(item => Date.parse(item.at) <= now.getTime()).sort((a,b) => Date.parse(b.at) - Date.parse(a.at));
  return { upcoming, due, next: upcoming[0], departed, available };
}
export function formatReminderTime(at: string, booking: ReminderBooking): string {
  const zone = getTripSchedule(booking)?.timeZone;
  return new Intl.DateTimeFormat('ru-RU', { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone: zone ?? 'UTC' }).format(new Date(at));
}
