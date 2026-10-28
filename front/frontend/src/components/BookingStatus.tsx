import { useEffect, useState } from 'react';
import { ArrowRight, Bell, CheckCheck, Info } from 'lucide-react';
import type { Session } from '../types';
import { formatReminderTime, getReminderState, initialReminderSettings } from '../reminders/model';
import { shortDate } from './TripCard';

export function BookingStatus({session:s,onOpen}:{session:Session;onOpen:()=>void}) {
  const [now,setNow] = useState(()=>new Date());
  useEffect(()=>{const update=()=>setNow(new Date());const timer=window.setInterval(update,30000);document.addEventListener('visibilitychange',update);return()=>{window.clearInterval(timer);document.removeEventListener('visibilitychange',update);};},[]);
  if(!s.booking || s.booking.status==='cancelled') return null;
  if(!s.booked || s.booking.status!=='confirmed') return <div className="booking-status paused"><Info size={16}/><span>План изменён. Прежние напоминания отключены.</span><button onClick={onOpen}>Проверить<ArrowRight size={13}/></button></div>;
  const settings=s.reminderSettings ?? initialReminderSettings();
  const reminder=getReminderState(s.booking,settings,now);
  return <section className={`booked-banner booking-status ${reminder.due.length ? 'reminder-is-due' : ''}`} aria-label="Ваша оформленная демо-поездка" role={reminder.due.length ? 'status' : undefined}>
    {reminder.due.length ? <Bell size={17}/> : <CheckCheck size={18}/>}
    <div><strong>Демо-поездка оформлена · {s.booking.result.trip.city}{s.booking.preferences.startDate ? ` · ${shortDate(s.booking.preferences.startDate)}` : ''}</strong>
      <p>{reminder.due.length ? 'Наступило напоминание: пора проверить детали поездки.' : reminder.next ? `Ближайшее напоминание: ${formatReminderTime(reminder.next.at,s.booking)} · время города отправления` : 'Без настоящей брони и оплаты.'}</p></div>
    <button onClick={onOpen}>{settings.enabled ? 'Открыть' : 'Поездка и напоминания'}<ArrowRight size={13}/></button>
  </section>;
}
