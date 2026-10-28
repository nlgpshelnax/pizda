import { describe, expect, it } from 'vitest';
import { trips } from '../src/data/trips';
import { initialPreferences } from '../src/state/initial';
import { calculateCosts, totalCosts } from '../src/agent/ranking';
import { buildTripCalendar, escapeCalendarText, foldCalendarLine } from '../src/reminders/calendar';
import { getReminderState, getTripSchedule, initialReminderSettings, reconcileReminderSettings, reminderTime, reminderUnavailableReason, saveReminderSettings } from '../src/reminders/model';
import type { ReminderBooking } from '../src/reminders/model';

function booking(date = '2026-12-12', origin = 'Москва', tripId = 'rome'): ReminderBooking {
  const preferences = initialPreferences();
  preferences.startDate = date; preferences.nights = 6;
  preferences.slots.origin = { value: origin, status:'YES' };
  const trip = trips.find(t => t.id === tripId)!;
  const costs = calculateCosts(trip, preferences);
  return { id:'booking-test', confirmedAt:'2026-10-26T12:00:00.000Z', preferences, result: { trip, costs, total:totalCosts(costs), score:100, reasons:[], compromises:[] } };
}
const early = new Date('2026-10-26T12:00:00Z');
const unfold = (value: string) => value.replace(/\r\n /g, '');
describe('Browser reminder schedule', () => {
  it('starts disabled and uses an exact departure rather than midnight', () => {
    expect(initialReminderSettings().enabled).toBe(false);
    const b = booking(); const route = getTripSchedule(b)!;
    expect(route.departureAt).toBe('2026-12-12T04:30:00.000Z');
    const settings = saveReminderSettings(b, true, ['7d','1d','3h'], early);
    expect(settings.schedule.map(r=>r.at)).toEqual(['2026-12-05T04:30:00.000Z','2026-12-11T04:30:00.000Z','2026-12-12T01:30:00.000Z']);
    expect(settings.enabled).toBe(true);
  });
  it('supports several offsets, deduplicates, and switches off', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['7d','7d','3h'],early);
    expect(settings.offsets).toEqual(['7d','3h']); expect(settings.schedule).toHaveLength(2);
    const disabled = saveReminderSettings(b,false,settings.offsets,early);
    expect(disabled.enabled).toBe(false); expect(disabled.schedule).toEqual([]);
  });
  it('does not create triggers for a time in the past or exactly now', () => {
    const b = booking(); const now = new Date('2026-12-11T04:30:00Z');
    const settings = saveReminderSettings(b,true,['7d','1d','3h'],now);
    expect(settings.schedule).toEqual([{offset:'3h',at:'2026-12-12T01:30:00.000Z'}]);
    const late = saveReminderSettings(b,true,['7d'],now); expect(late.enabled).toBe(false); expect(late.schedule).toEqual([]);
  });
  it('preserves a saved schedule across reload and can show a due reminder without claiming delivery', () => {
    const b = booking(); const original = saveReminderSettings(b,true,['7d','1d','3h'],early);
    const restored = JSON.parse(JSON.stringify(original));
    const reconciled = reconcileReminderSettings(b,restored,true,new Date('2026-12-06T04:30:00Z'));
    expect(reconciled.schedule).toEqual(original.schedule);
    const state = getReminderState(b,reconciled,new Date('2026-12-06T04:30:00Z'));
    expect(state.due.map(r=>r.offset)).toEqual(['7d']); expect(state.next?.offset).toBe('1d');
  });
  it('recalculates when the route date changes, keeping selected intervals', () => {
    const before = booking(); const after = booking('2026-12-14');
    const settings = saveReminderSettings(before,true,['7d','3h'],early);
    const revised = reconcileReminderSettings(after,settings,true,early);
    expect(revised.offsets).toEqual(['7d','3h']);
    expect(Date.parse(revised.schedule[0].at)-Date.parse(settings.schedule[0].at)).toBe(2*86400000);
  });
  it('pauses after cancellation/invalidation and does not reactivate a cancelled schedule on reopening', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['7d','3h'],early);
    const paused = reconcileReminderSettings(b,settings,false,early);
    expect(paused.enabled).toBe(false); expect(paused.schedule).toEqual([]); expect(paused.offsets).toEqual(['7d','3h']);
    const reopened = reconcileReminderSettings({...b,id:'new-booking'},paused,true,early);
    expect(reopened.enabled).toBe(false); expect(reopened.schedule).toEqual([]);
  });
  it('does not show due notifications after departure', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['1d'],early);
    const state = getReminderState(b,settings,new Date('2026-12-12T04:30:00Z'));
    expect(state.departed).toBe(true); expect(state.due).toEqual([]); expect(state.next).toBeUndefined();
  });
  it('declines approximate dates and unknown origin time zones', () => {
    const b = booking(); b.preferences.startDate = undefined;
    expect(getTripSchedule(b)).toBeNull(); expect(saveReminderSettings(b,true,['1d'],early).schedule).toEqual([]);
    const unknown = booking('2026-12-12','Антананариву');
    expect(getTripSchedule(unknown)).toBeNull(); expect(reminderUnavailableReason(unknown)).toContain('часовой пояс');
    expect(()=>buildTripCalendar(unknown,initialReminderSettings(),early)).toThrow();
  });
  it('validates dates instead of normalizing impossible days', () => {
    expect(getTripSchedule(booking('2026-02-30'))).toBeNull();
    expect(getTripSchedule(booking('not-a-date'))).toBeNull();
  });
  it('uses destination daylight saving time and absolute offsets across DST boundary', () => {
    const winter = getTripSchedule(booking('2026-12-12'))!;
    const summer = getTripSchedule(booking('2027-07-12'))!;
    expect(winter.departureAt.slice(11,16)).toBe('04:30'); expect(summer.departureAt.slice(11,16)).toBe('03:30');
    const b = booking('2027-03-30');
    expect(Date.parse(getTripSchedule(b)!.departureAt) - Date.parse(reminderTime(b,'7d')!)).toBe(7*86400000);
  });
  it('local origin changes do not reinterpret the UTC departure as Moscow midnight', () => {
    const moscow = getTripSchedule(booking())!; const ekb = getTripSchedule(booking('2026-12-12','Екатеринбург'))!;
    expect(ekb.departureAt).toBe(moscow.departureAt); expect(ekb.timeZone).toBe('Asia/Yekaterinburg');
  });
});
describe('iCalendar export', () => {
  it('contains UTC trip span, direction and multi alarms with CRLF', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['7d','1d','3h'],early);
    const ics = buildTripCalendar(b,settings,early); const text = unfold(ics);
    expect(text).toContain('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n');
    expect(text).toContain('DTSTART:20261212T043000Z'); expect(text).toContain('DTEND:20261218T231000Z');
    expect(text).toContain('LOCATION:Рим\\, Италия'); expect(text).toContain('SUMMARY:Рим без спешки · Рим (демо)');
    expect(text.match(/BEGIN:VALARM/g)).toHaveLength(3);
    expect(text).toContain('TRIGGER;RELATED=START:-P7D'); expect(text).toContain('TRIGGER;RELATED=START:-P1D'); expect(text).toContain('TRIGGER;RELATED=START:-PT3H');
    expect(ics.replace(/\r\n/g,'')).not.toMatch(/[\r\n]/);
  });
  it('exports no alarm when disabled or elapsed, and keeps a future alarm only', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['7d','1d','3h'],early);
    expect(buildTripCalendar(b,{...settings,enabled:false},early)).not.toContain('BEGIN:VALARM');
    const later = buildTripCalendar(b,settings,new Date('2026-12-11T04:30:00Z'));
    expect(later.match(/BEGIN:VALARM/g)).toHaveLength(1); expect(later).toContain('-PT3H');
    expect(buildTripCalendar(b,settings,new Date('2026-12-20T00:00:00Z'))).not.toContain('BEGIN:VALARM');
  });
  it('does not reuse old alarms for a new date before reconciliation', () => {
    const b = booking(); const settings = saveReminderSettings(b,true,['1d'],early);
    expect(buildTripCalendar(booking('2026-12-14'),settings,early)).not.toContain('BEGIN:VALARM');
  });
  it('escapes delimiters, line breaks and backslashes to prevent property injection', () => {
    expect(escapeCalendarText('A,B;C\\D\r\nEND:VEVENT')).toBe('A\\,B\\;C\\\\D\\nEND:VEVENT');
    const b = booking(); b.result = structuredClone(b.result); b.result.trip.title = 'Море; кофе, закат\nBEGIN:VALARM';
    const text = unfold(buildTripCalendar(b,initialReminderSettings(),early));
    expect(text).toContain('SUMMARY:Море\\; кофе\\, закат\\nBEGIN:VALARM');
    expect(text.match(/\r\nBEGIN:VALARM/g)).toBeNull();
  });
  it('folds long Unicode properties at 75 bytes and round-trips without text loss', () => {
    const line = 'SUMMARY:' + 'Путешествие к морю, горам и музеям '.repeat(8) + '✈️';
    const folded = foldCalendarLine(line);
    const encoder = new TextEncoder();
    expect(folded.split('\r\n').every(part=>encoder.encode(part).length<=75)).toBe(true);
    expect(unfold(folded)).toBe(line);
  });
  it('keeps a stable safe UID for the same confirmed booking', () => {
    const b = booking(); const settings = initialReminderSettings();
    const first = buildTripCalendar(b,settings,early).match(/UID:([^\r]+)/)?.[1];
    const second = buildTripCalendar(b,settings,new Date('2026-10-27T00:00:00Z')).match(/UID:([^\r]+)/)?.[1];
    expect(first).toBe(second); expect(first).toMatch(/^odin-[a-f0-9]+@demo\.odin-travel\.local$/);
  });
});
