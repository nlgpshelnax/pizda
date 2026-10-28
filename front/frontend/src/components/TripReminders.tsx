import { notify } from './Toast';
import { useEffect, useState } from 'react';
import { Bell, CalendarPlus, Check, ChevronDown } from 'lucide-react';
import { downloadTripCalendar } from '../reminders/calendar';
import { formatReminderTime, getReminderState, getTripSchedule, reminderOptions, reminderTime, reminderUnavailableReason, saveReminderSettings } from '../reminders/model';
import type { ReminderBooking, ReminderOffset, ReminderSettings } from '../reminders/model';

export interface TripRemindersProps {
  booking: ReminderBooking;
  settings: ReminderSettings;
  onChange: (settings: ReminderSettings) => void;
  active?: boolean;
}
export function TripReminders({ booking, settings, onChange, active = true }: TripRemindersProps) {
  const [enabled, setEnabled] = useState(settings.enabled);
  const [offsets, setOffsets] = useState<ReminderOffset[]>(settings.offsets);
  const [editing, setEditing] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const updateClock = () => setNow(new Date());
    const timer = window.setInterval(updateClock, 30000);
    document.addEventListener('visibilitychange', updateClock);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', updateClock); };
  }, []);
  useEffect(() => { setEnabled(settings.enabled); setOffsets(settings.offsets); }, [settings.enabled, settings.savedAt, settings.routeKey, settings.offsets]);
  const route = getTripSchedule(booking);
  const state = getReminderState(booking, settings, now);
  const available = active && !!route && !state.departed;
  const selected = new Set(offsets);
  const futureOptions = reminderOptions.filter(option => { const at = reminderTime(booking, option.offset); return at && Date.parse(at) > now.getTime(); });
  const canSave = enabled && futureOptions.some(option => selected.has(option.offset));
  const hasChanges = enabled !== settings.enabled || reminderOptions.some(option => selected.has(option.offset) !== settings.offsets.includes(option.offset));
  const toggle = (value: boolean) => {
    setEnabled(value); setFeedback('');
    if (!value) { onChange(saveReminderSettings(booking, false, offsets, now)); setEditing(false); }
    else {
      const choices = futureOptions.map(option => option.offset);
      if (!offsets.some(offset => choices.includes(offset))) setOffsets(choices.includes('1d') ? ['1d'] : choices.slice(-1));
      setEditing(true);
    }
  };
  const save = () => {
    const next = saveReminderSettings(booking, enabled, offsets, new Date());
    onChange(next); setEnabled(next.enabled); setOffsets(next.offsets); setEditing(false);
    if(next.enabled) notify('Напоминания обновлены.');
    setFeedback(next.enabled ? 'Настройки сохранены в этом браузере.' : 'Будущего времени для выбранных напоминаний уже нет.');
  };
  return <section className="trip-reminders" aria-label="Напоминания о поездке">
    <div className="reminders-heading"><h3><Bell size={17} />Напомнить о поездке</h3><label className="reminder-toggle"><input type="checkbox" role="switch" aria-label="Включить напоминания о поездке" checked={enabled && active} disabled={!available} onChange={e => toggle(e.target.checked)} /><span>{enabled && active ? 'Включены' : 'Выключены'}</span></label></div>
    {!available ? <p className="reminder-help">{!active ? 'Бронирование изменено или отменено. Напоминания отключены до нового оформления.' : state.departed ? 'Отправление уже состоялось. Новые напоминания не создаются.' : reminderUnavailableReason(booking) ?? 'Для напоминаний нужно уточнить маршрут.'}</p> : <>
      {settings.enabled && !editing && <div className="reminder-summary"><p>{state.next ? <>Ближайшее: <strong>{formatReminderTime(state.next.at, booking)}</strong></> : 'Все настроенные времена уже наступили.'}</p><button type="button" className="text-link" onClick={() => { setEditing(true); setFeedback(''); }}>Изменить <ChevronDown size={12} /></button></div>}
      {state.due.length > 0 && <p className="reminder-due" role="status"><Bell size={13} />Время проверить детали поездки. Отправление {formatReminderTime(route!.departureAt, booking)}.</p>}
      {enabled && (editing || !settings.enabled) && <div className="reminder-options">{reminderOptions.map(option => {
        const at = reminderTime(booking, option.offset); const past = !at || Date.parse(at) <= now.getTime();
        return <label className={`reminder-option${past ? ' reminder-option-past' : ''}`} key={option.offset}><input type="checkbox" checked={selected.has(option.offset) && !past} disabled={past} onChange={e => { setFeedback(''); setOffsets(previous => e.target.checked ? [...previous, option.offset] : previous.filter(offset => offset !== option.offset)); }} /><span>{option.label}<small>{past ? 'Это время уже прошло' : formatReminderTime(at!, booking)}</small></span></label>;
      })}<button type="button" className="secondary-button" disabled={!canSave} onClick={save}>Сохранить напоминания</button></div>}
      {settings.enabled && !editing && <p className="reminder-saved-times">{settings.schedule.map(item => `${reminderOptions.find(o => o.offset === item.offset)?.label}: ${formatReminderTime(item.at, booking)}`).join(' · ')}</p>}
      <p className="reminder-help">Время города отправления: {booking.preferences.slots.origin.value}. Напоминания на сайте видны при его использовании; при закрытом сайте уведомлений нет. Для напоминаний вне сайта добавьте событие в календарь.</p>
    </>}
    <div className="reminder-actions"><button type="button" className="text-link" disabled={!active || !route || (editing && hasChanges)} onClick={() => { try { downloadTripCalendar(booking, settings); setFeedback('Файл календаря скачан. Импортируйте его в свой календарь.'); } catch { setFeedback('Нужно уточнить маршрут перед экспортом.'); } }}><CalendarPlus size={15} />Скачать событие .ics</button><small>Файл не обновляется автоматически.</small></div>
    {feedback && <p className="reminder-feedback" role="status"><Check size={12} />{feedback}</p>}
  </section>;
}
