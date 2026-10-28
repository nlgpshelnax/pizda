import type { Session } from '../types';
import { initialSession } from './initial';
export const storageKey = 'odin-travel-session-v2';
const isResult = (r: Session['selectedResult']) => !!r?.trip?.hotel && typeof r.trip.id === 'string' && typeof r.total === 'number' && Number.isFinite(r.total) && !!r.costs && Array.isArray(r.reasons) && Array.isArray(r.compromises);
export function parseSavedSession(raw: string | null): Session | undefined {
  if (!raw) return;
  try {
    const candidate = JSON.parse(raw) as Session;
    const valid = candidate && candidate.preferences && ['when','origin','destination','purpose'].every(key => {
      const slot = candidate.preferences.slots?.[key as keyof typeof candidate.preferences.slots];
      return slot && typeof slot.value === 'string' && ['YES','Vague','NO'].includes(slot.status);
    });
    if (!valid || !Array.isArray(candidate.messages) || !Array.isArray(candidate.results) || !Array.isArray(candidate.conflicts) || !Array.isArray(candidate.preferences.purposes)) return;
    if (!Number.isInteger(candidate.preferences.guests) || candidate.preferences.guests < 1 || candidate.preferences.guests > 6 || !Number.isInteger(candidate.preferences.nights) || candidate.preferences.nights < 1 || candidate.preferences.nights > 30) return;
    if (candidate.messages.some(m => !m || !['agent','user'].includes(m.role) || typeof m.text !== 'string')) return;
    if (candidate.results.some(r => !isResult(r))) return;
    if (candidate.selectedResult && !isResult(candidate.selectedResult)) candidate.selectedResult = undefined;
    if (candidate.booking && (!isResult(candidate.booking.result) || !candidate.booking.preferences?.slots?.origin || !Array.isArray(candidate.booking.preferences.purposes) || !['confirmed','needs-confirmation','cancelled'].includes(candidate.booking.status) || !Number.isFinite(Date.parse(candidate.booking.confirmedAt)))) {
      candidate.booking = undefined;candidate.booked=false;
    }
    const reminders=candidate.reminderSettings;
    if (reminders && (!Array.isArray(reminders.offsets) || !Array.isArray(reminders.schedule) || typeof reminders.enabled !== 'boolean' || typeof reminders.routeKey !== 'string' || reminders.schedule.some(item=>!item || !['7d','1d','3h'].includes(item.offset) || !Number.isFinite(Date.parse(item.at))))) candidate.reminderSettings=undefined;
    return { ...initialSession(), ...candidate };
  } catch { return; }
}
