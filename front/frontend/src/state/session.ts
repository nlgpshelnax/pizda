import type { AgentResponse, Session } from '../types';
import { initialReminderSettings, reconcileReminderSettings } from '../reminders/model';
export function applyResponse(session: Session, response: AgentResponse): Session {
  const selectedStillFits = response.results.some(r => r.trip.id === session.selectedId);
  const tripChanges = response.changes.filter(change=>change !== 'pendingInput');
  const ancillaryOnly = tripChanges.length > 0 && tripChanges.every(c => c === 'earlyCheckin' || c === 'transfer');
  const booked = session.booked && selectedStillFits && (tripChanges.length === 0 || ancillaryOnly);
  const booking = session.booking ? { ...session.booking, status: booked ? 'confirmed' as const : session.booking.status === 'cancelled' ? 'cancelled' as const : 'needs-confirmation' as const,
    ...(booked ? { preferences: response.preferences, result: response.results.find(r => r.trip.id === session.booking?.result.trip.id) ?? session.booking.result } : {}) } : undefined;
  return {
    ...session, preferences: response.preferences, results: response.results, conflicts: response.conflicts,
    canSearch: response.canSearch, revision: session.revision + (response.changes.length > 0 ? 1 : 0),
    activeId: response.results.some(r => r.trip.id === session.activeId) ? session.activeId : response.results[0]?.trip.id,
    selectedId: selectedStillFits ? session.selectedId : undefined,
    booked,
    selectedResult: response.results.find(r => r.trip.id === session.selectedId),
    booking,
    reminderSettings: reconcileReminderSettings(booking, session.reminderSettings ?? initialReminderSettings(), booked),
  };
}
