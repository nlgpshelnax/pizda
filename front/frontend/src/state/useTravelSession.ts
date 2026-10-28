import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentAdapter, Session, SlotKey } from '../types';
import { initialSession } from './initial';
import { applyResponse } from './session';
import { HttpAgentAdapter } from '../agent/adapter';
import { parseSavedSession, storageKey } from './persistence';
import { rankTrips } from '../agent/ranking';
import { checkConflicts } from '../agent/conflicts';
import type { BookingDetailsPatch } from '../booking/review';
import { bookingBlockers, patchBookingPreferences, recalculateBooking } from '../booking/review';
import { initialReminderSettings, reconcileReminderSettings } from '../reminders/model';
import type { ReminderSettings } from '../reminders/model';

const defaultAgentAdapter: AgentAdapter = new HttpAgentAdapter();
function restore(): Session {
  try {
    const saved = parseSavedSession(localStorage.getItem(storageKey)) ?? parseSavedSession(sessionStorage.getItem('odin-travel-session-v1'));
    if (saved) {
      if(saved.booked && !saved.booking && saved.preferences.startDate) {
        const result=saved.selectedResult ?? saved.results.find(r=>r.trip.id===saved.selectedId);
        if(result) saved.booking={id:`migrated-${result.trip.id}-${saved.preferences.startDate}`,confirmedAt:new Date().toISOString(),result,preferences:structuredClone(saved.preferences),status:'confirmed'};
      }
      return { ...saved,booked:saved.booked && saved.booking?.status==='confirmed', reminderSettings: reconcileReminderSettings(saved.booking, saved.reminderSettings ?? initialReminderSettings(), saved.booked && saved.booking?.status === 'confirmed') };
    }
  } catch { /* Private browsing or malformed storage: use an empty session. */ }
  return initialSession();
}
/** Injection replaces chat transport only; booking and recalculation remain demo-local. */
export function useTravelSession(adapter: AgentAdapter = defaultAgentAdapter) {
  const [session, setSession] = useState<Session>(restore);
  const [busy, setBusy] = useState(false);
  const requestId = useRef(0);
  const sessionRef = useRef(session); sessionRef.current = session;
  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(session)); } catch { /* In-memory session remains usable. */ } }, [session]);
  const send = useCallback(async (value: string, slotContext?: SlotKey) => {
    const text = value.trim();
    if (!text || busy) return;
    const currentRequest = ++requestId.current;
    const current = sessionRef.current;
    setSession(s => ({ ...s, messages: [...s.messages, { id: crypto.randomUUID(), role: 'user', text }] }));
    setBusy(true);
    try {
      const response = await adapter.respond({ text, preferences: current.preferences, selectedId: current.selectedId, slotContext });
      if (requestId.current !== currentRequest) return;
      setSession(s => ({ ...applyResponse(s, response), messages: [...s.messages, { id: crypto.randomUUID(), role: 'agent', text: response.message }] }));
    } catch {
      if (requestId.current !== currentRequest) return;
      setSession(s => ({ ...s, messages: [...s.messages, { id: crypto.randomUUID(), role: 'agent', text: 'Не удалось обработать запрос. Ваши параметры сохранены. Попробуйте отправить сообщение ещё раз.' }] }));
    } finally { if (requestId.current === currentRequest) setBusy(false); }
  }, [busy, adapter]);
  const reset = () => { ++requestId.current; setBusy(false); setSession(initialSession()); };
  const activate = (id: string) => setSession(s => ({ ...s, activeId: id }));
  const select = (id: string) => setSession(s => ({ ...s, selectedId: id, selectedResult:s.results.find(r => r.trip.id === id), activeId: id }));
  const updateDetails = (patch: BookingDetailsPatch) => setSession(s => {
    const preferences = patchBookingPreferences(s.preferences, patch);
    const selected = s.selectedResult ?? s.results.find(r => r.trip.id === s.selectedId) ?? s.booking?.result;
    const selectedResult = selected ? recalculateBooking(selected, preferences) : undefined;
    const changed = JSON.stringify(preferences) !== JSON.stringify(s.preferences);
    const booking = s.booking && changed ? { ...s.booking, status:s.booking.status === 'cancelled' ? 'cancelled' as const : 'needs-confirmation' as const } : s.booking;
    return { ...s, preferences, selectedResult, selectedId:selectedResult?.trip.id ?? s.selectedId, conflicts:checkConflicts(preferences), results:rankTrips(preferences), booked: changed ? false : s.booked, booking,
      reminderSettings:reconcileReminderSettings(booking,s.reminderSettings ?? initialReminderSettings(), !changed && s.booked), revision:s.revision+(changed ? 1 : 0) };
  });
  const book = () => setSession(s => {
    const result = s.selectedResult ?? s.results.find(r => r.trip.id === s.selectedId);
    if (!result || bookingBlockers(result,s.preferences).length) return s;
    if (s.booked && s.booking?.status === 'confirmed' && s.booking.result.trip.id === result.trip.id) return s;
    const booking = { id:crypto.randomUUID(),confirmedAt:new Date().toISOString(),result:structuredClone(result),preferences:structuredClone(s.preferences),status:'confirmed' as const };
    return { ...s, booked:true, booking, reminderSettings:reconcileReminderSettings(booking,s.reminderSettings ?? initialReminderSettings(),true), messages:[...s.messages,{id:crypto.randomUUID(),role:'agent',text:'Демо-поездка оформлена. Оплаты и настоящего бронирования не было. План и напоминания можно открыть в «Моей поездке».'}] };
  });
  const cancelBooking = () => setSession(s => s.booking?.status !== 'confirmed' ? s : ({ ...s,booked:false,booking:s.booking ? {...s.booking,status:'cancelled'} : undefined,
    reminderSettings:reconcileReminderSettings(s.booking,s.reminderSettings ?? initialReminderSettings(),false),
    messages:[...s.messages,{id:crypto.randomUUID(),role:'agent',text:'Демо-бронирование отменено. Связанные напоминания отключены. Параметры и переписка сохранены.'}] }));
  const setReminders = (reminderSettings: ReminderSettings) => setSession(s => ({...s,reminderSettings}));
  const beginBookingEdit = () => setSession(s => s.booking?.status === 'confirmed' ? {...s,preferences:structuredClone(s.booking.preferences),selectedId:s.booking.result.trip.id,selectedResult:structuredClone(s.booking.result),activeId:s.booking.result.trip.id,results:rankTrips(s.booking.preferences),conflicts:checkConflicts(s.booking.preferences)} : s);
  return { session, busy, send, reset, activate, select, book, updateDetails, cancelBooking, setReminders, beginBookingEdit };
}
