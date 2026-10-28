import { getTripSchedule, reminderOptions, reminderUnavailableReason } from './model';
import type { ReminderBooking, ReminderSettings } from './model';

export function escapeCalendarText(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/\r\n|\r|\n/g, '\\n').replace(/;/g, '\\;').replace(/,/g, '\\,');
}
/** RFC 5545 lines are folded at 75 UTF-8 octets, never in the middle of a Unicode character. */
export function foldCalendarLine(value: string): string {
  const encoder = new TextEncoder();
  const lines: string[] = [];
  let line = ''; let bytes = 0;
  for (const character of value) {
    const size = encoder.encode(character).length;
    if (bytes + size > 75) { lines.push(line); line = ' '; bytes = 1; }
    line += character; bytes += size;
  }
  lines.push(line);
  return lines.join('\r\n');
}
const utc = (value: string | Date) => new Date(value).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
function uid(id: string): string {
  let hash = 2166136261;
  for (const character of id) hash = Math.imul(hash ^ character.codePointAt(0)!, 16777619) >>> 0;
  return `odin-${hash.toString(16)}@demo.odin-travel.local`;
}
export function buildTripCalendar(booking: ReminderBooking, settings: ReminderSettings, now = new Date()): string {
  const route = getTripSchedule(booking);
  if (!route) throw new Error(reminderUnavailableReason(booking) ?? 'Маршрут не содержит корректного времени отправления.');
  const t = booking.result.trip;
  const description = [
    `Демонстрационная поездка. Настоящие билеты и отель не забронированы.`,
    `Направление: ${t.country}, ${t.city}. Отель: ${t.hotel.name}.`,
    `Даты пребывания: ${route.startDate} — ${route.endDate}, ${booking.preferences.nights} ночей.`,
    `Отправление из ${booking.preferences.slots.origin.value}. Событие включает дорогу и возвращение домой.`,
    `Скачанный файл является копией и не обновляется автоматически при изменении плана на сайте.`,
  ].join('\n');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Odin Travel//Demo trip planner//RU', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    'BEGIN:VEVENT', `UID:${uid(booking.id)}`, `DTSTAMP:${utc(now)}`, `CREATED:${utc(booking.confirmedAt)}`, `LAST-MODIFIED:${utc(now)}`,
    `DTSTART:${utc(route.departureAt)}`, `DTEND:${utc(route.returnAt)}`,
    `SUMMARY:${escapeCalendarText(`${t.title} · ${t.city} (демо)`)}`, `LOCATION:${escapeCalendarText(`${t.city}, ${t.country}`)}`,
    `DESCRIPTION:${escapeCalendarText(description)}`, 'STATUS:TENTATIVE', 'TRANSP:OPAQUE',
  ];
  if (settings.enabled && settings.routeKey === route.routeKey && Date.parse(route.departureAt) > now.getTime()) {
    // Export only saved, unchanged, future alarms. Never revive a trigger that was skipped at save time.
    for (const item of settings.schedule) {
      const option = reminderOptions.find(o => o.offset === item.offset);
      if (!option || !Number.isFinite(Date.parse(item.at)) || Date.parse(item.at) <= now.getTime()) continue;
      const expected = Date.parse(route.departureAt) - option.milliseconds;
      if (expected !== Date.parse(item.at)) continue;
      lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', `TRIGGER;RELATED=START:${option.trigger}`, `DESCRIPTION:${escapeCalendarText(`Поездка в ${t.city} · ${option.label.toLowerCase()} до отправления (демо)`)}`, 'END:VALARM');
    }
  }
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.map(foldCalendarLine).join('\r\n') + '\r\n';
}
export function downloadTripCalendar(booking: ReminderBooking, settings: ReminderSettings, now = new Date()): void {
  const calendar = buildTripCalendar(booking, settings, now);
  const url = URL.createObjectURL(new Blob([calendar], { type:'text/calendar;charset=utf-8' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `odin-${booking.result.trip.id}.ics`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
