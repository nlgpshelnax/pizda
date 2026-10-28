import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';
import './date-field.css';

interface Props { value: string; min: string; error?: string; onChange: (value: string) => void }

const parse = (value: string) => new Date(`${value}T12:00:00Z`);
const iso = (date: Date) => date.toISOString().slice(0, 10);
const moveDays = (value: string, days: number) => { const date = parse(value); date.setUTCDate(date.getUTCDate() + days); return iso(date); };
function moveMonths(value: string, months: number) {
  const date = parse(value);
  const day = date.getUTCDate();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() + months);
  const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, last));
  return iso(date);
}
const longDate = (value: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parse(value));

export function DateField({ value, min, error, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(value && value >= min ? value : min);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const activeDay = useRef<HTMLButtonElement>(null);
  const chosen = value && Number.isFinite(parse(value).getTime()) ? value : '';

  useEffect(() => {
    if (!open) return;
    const node = dialog.current;
    node?.showModal();
    if (node && trigger.current) {
      const anchor = trigger.current.getBoundingClientRect();
      const box = node.getBoundingClientRect();
      const left = Math.max(12, Math.min(anchor.right - box.width, window.innerWidth - box.width - 12));
      const below = anchor.bottom + 6;
      const top = below + box.height <= window.innerHeight - 12 ? below : Math.max(12, anchor.top - box.height - 6);
      node.style.left = `${left}px`;
      node.style.top = `${top}px`;
    }
    activeDay.current?.focus();
    return () => { if (node?.open) node.close(); };
  }, [open]);

  const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current?.focus()); };
  const openCalendar = () => { setActive(chosen && chosen >= min ? chosen : min); setOpen(true); };
  const navigate = (date: string) => { setActive(date < min ? min : date); requestAnimationFrame(() => activeDay.current?.focus()); };
  const activeDate = parse(active);
  const year = activeDate.getUTCFullYear();
  const month = activeDate.getUTCMonth();
  const firstDay = new Date(Date.UTC(year, month, 1));
  const offset = (firstDay.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const heading = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(firstDay).replace(/\s*г\.$/, '');
  const previousMonthAvailable = `${year}-${String(month + 1).padStart(2, '0')}` > min.slice(0, 7);
  const onDayKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const weekday = (parse(active).getUTCDay() + 6) % 7;
    let next: string | undefined;
    if (event.key === 'ArrowLeft') next = moveDays(active, -1);
    else if (event.key === 'ArrowRight') next = moveDays(active, 1);
    else if (event.key === 'ArrowUp') next = moveDays(active, -7);
    else if (event.key === 'ArrowDown') next = moveDays(active, 7);
    else if (event.key === 'Home') next = moveDays(active, -weekday);
    else if (event.key === 'End') next = moveDays(active, 6 - weekday);
    else if (event.key === 'PageUp') next = moveMonths(active, event.shiftKey ? -12 : -1);
    else if (event.key === 'PageDown') next = moveMonths(active, event.shiftKey ? 12 : 1);
    if (next) { event.preventDefault(); navigate(next); }
  };

  return <div className="booking-date-field">
    <label htmlFor="booking-date">Дата начала</label>
    <div className="date-input-wrap">
      <input id="booking-date" aria-label="Дата начала" className="date-input" type="date" value={value} min={min} onChange={event => onChange(event.target.value)} onKeyDown={event => { if (event.altKey && event.key === 'ArrowDown') { event.preventDefault(); openCalendar(); } }} aria-invalid={!!error} aria-describedby={error ? 'booking-date-error' : undefined} required />
      <button ref={trigger} type="button" className="date-picker-trigger" onClick={openCalendar} aria-label="Открыть календарь" aria-haspopup="dialog"><CalendarDays size={19} aria-hidden="true" /></button>
    </div>
    {error && <small className="field-error" id="booking-date-error">{error}</small>}
    {open && <dialog ref={dialog} className="date-picker" aria-label="Выберите дату начала" onCancel={event => { event.preventDefault(); event.stopPropagation(); close(); }} onClick={event => { if (event.target === dialog.current) close(); }}>
      <div className="date-picker-inner">
        <div className="date-picker-title"><div><h2>Дата начала</h2><p>{chosen ? `Выбрано: ${longDate(chosen)}` : 'Выберите день поездки'}</p></div><button type="button" onClick={close} aria-label="Закрыть календарь"><X size={19} aria-hidden="true" /></button></div>
        <div className="date-picker-month"><button type="button" disabled={!previousMonthAvailable} onClick={() => navigate(moveMonths(active, -1))} aria-label="Предыдущий месяц"><ChevronLeft size={19} aria-hidden="true" /></button><strong aria-live="polite">{heading}</strong><button type="button" onClick={() => navigate(moveMonths(active, 1))} aria-label="Следующий месяц"><ChevronRight size={19} aria-hidden="true" /></button></div>
        <div className="date-weekdays" aria-hidden="true">{['пн','вт','ср','чт','пт','сб','вс'].map(day => <span key={day}>{day}</span>)}</div>
        <div className="date-days" role="group" aria-label={`Дни: ${heading}`} onKeyDown={onDayKey}>
          {Array.from({ length: offset }, (_, i) => <span key={`empty-${i}`} aria-hidden="true" />)}
          {Array.from({ length: count }, (_, i) => { const day = `${year}-${String(month + 1).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`; return <button key={day} ref={day === active ? activeDay : undefined} type="button" tabIndex={day === active ? 0 : -1} disabled={day < min} aria-label={longDate(day)} aria-pressed={day === chosen} aria-current={day === min ? 'date' : undefined} className={day === chosen ? 'is-selected' : ''} onClick={() => { onChange(day); close(); }}>{i + 1}</button>; })}
        </div>
        <p className="date-picker-help">Стрелки — выбор дня, Page Up / Page Down — месяц</p>
      </div>
    </dialog>}
  </div>;
}
