import { describe, expect, it } from 'vitest';
import { initialPreferences, initialSession } from '../src/state/initial';
import { parseMessage } from '../src/agent/parser';
import { calculateCosts, rankTrips, totalCosts } from '../src/agent/ranking';
import { bookingBlockers, patchBookingPreferences, recalculateBooking, validateBookingFields } from '../src/booking/review';
import { parseSavedSession } from '../src/state/persistence';
import { applyResponse } from '../src/state/session';
import { processRequest } from '../src/agent/adapter';
import { initialReminderSettings, saveReminderSettings } from '../src/reminders/model';

const now = new Date('2026-10-26T12:00:00Z');
const preferences = () => parseMessage('12 декабря из Москвы в Сербию, прогулки, 1 взрослый',initialPreferences()).preferences;
describe('Мгновенный расчёт формы без обращения к агенту',()=>{
  it('обновляет только указанные поля и сохраняет предпочтения',()=>{
    const p=preferences();const updated=patchBookingPreferences(p,{startDate:'2026-12-14',guests:2,guestsEstimated:false});
    expect(updated.startDate).toBe('2026-12-14');expect(updated.slots.when.value).toContain('14 декабря');expect(updated.slots.destination).toEqual(p.slots.destination);expect(updated.guests).toBe(2);
  });
  it('пересчитывает все статьи расходов из текущих гостей и города',()=>{
    const p=preferences(), r=rankTrips(p)[0];const updated=patchBookingPreferences(p,{guests:2,origin:'Екатеринбург'});const next=recalculateBooking(r,updated);
    expect(next.costs).toEqual(calculateCosts(r.trip,updated));expect(next.total).toBe(totalCosts(next.costs));expect(next.total).toBeGreaterThan(r.total);expect(next.trip.id).toBe(r.trip.id);
  });
  it('не переключает отель и блокирует бюджетный конфликт',()=>{
    const p=preferences(),r=rankTrips(p)[0];const nextP={...p,guests:6,budget:r.total};const next=recalculateBooking(r,nextP);
    expect(next.trip.id).toBe(r.trip.id);expect(bookingBlockers(next,nextP,now).some(x=>x.includes('превышает'))).toBe(true);
  });
  it('не оформляет старый снимок отеля для нового направления',()=>{
    const p=preferences(),r=rankTrips(p)[0];const changed=parseMessage('Вместо этого в Испанию',p).preferences;
    expect(bookingBlockers(r,changed,now).some(message=>message.includes('новому направлению'))).toBe(true);
  });
  it('не превращает пустой/невалидный ввод гостей в одного взрослого',()=>{
    for(const guests of ['', '0','7','-1','1.5','NaN']) expect(validateBookingFields({date:'2026-12-12',origin:'Москва',guests},now).guests).toBeDefined();
  });
  it('не принимает прошедшую или невозможную дату',()=>{
    for(const date of ['','2026-02-31','2026-10-25']) expect(validateBookingFields({date,origin:'Москва',guests:'1'},now).date).toBeDefined();
  });
  it('сохраняет неизвестный город без выдуманного расчёта маршрута',()=>{
    const p=patchBookingPreferences(preferences(),{origin:'Антананариву'});
    expect(p.slots.origin.value).toBe('Антананариву');expect(p.slots.origin.status).toBe('YES');expect(p.slots.origin.catalogSupport).toBe('unsupported');
    expect(validateBookingFields({date:'2026-12-12',guests:'1',origin:p.slots.origin.value},now).origin).toContain('нет расчёта');expect(bookingBlockers(recalculateBooking(rankTrips(preferences())[0],p),p,now).length).toBeGreaterThan(0);
  });
});
describe('Снимок бронирования и сохранение',()=>{
  it('восстанавливает поездку, выбранные настройки и снимок вне текущего top-5',()=>{
    const p=preferences(),result=rankTrips(p)[0];const booking={id:'booking-1',confirmedAt:now.toISOString(),result,preferences:p,status:'confirmed' as const};
    const s={...initialSession(),preferences:p,results:[],booked:true,booking,reminderSettings:saveReminderSettings(booking,true,['7d','1d','3h'],now)};
    const restored=parseSavedSession(JSON.stringify(s));expect(restored?.booking?.id).toBe('booking-1');expect(restored?.booking?.result).toEqual(result);expect(restored?.reminderSettings?.schedule).toHaveLength(3);
  });
  it('безопасно отклоняет испорченное сохранение',()=>{for(const raw of ['{bad','null','{}','{"messages":[]}'])expect(parseSavedSession(raw)).toBeUndefined();});
  it('перенос даты приостанавливает прежние напоминания без потери выбора интервалов',()=>{
    const p=preferences(),result=rankTrips(p)[0],booking={id:'booking-1',confirmedAt:now.toISOString(),result,preferences:p,status:'confirmed' as const};
    const s={...initialSession(),preferences:p,results:rankTrips(p),selectedId:result.trip.id,selectedResult:result,booked:true,booking,reminderSettings:saveReminderSettings(booking,true,['7d','1d'],now)};
    const next=applyResponse(s,processRequest({text:'На два дня позже',preferences:p,selectedId:result.trip.id}));
    expect(next.booked).toBe(false);expect(next.booking?.status).toBe('needs-confirmation');expect(next.booking?.preferences.startDate).toBe('2026-12-12');expect(next.preferences.startDate).toBe('2026-12-14');
    expect(next.reminderSettings?.enabled).toBe(false);expect(next.reminderSettings?.schedule).toEqual([]);expect(next.reminderSettings?.offsets).toEqual(['7d','1d']);
  });
  it('необязательный ранний заезд сохраняет бронь и расписание',()=>{
    const p=preferences(),result=rankTrips(p)[0],booking={id:'booking-1',confirmedAt:now.toISOString(),result,preferences:p,status:'confirmed' as const};
    const settings=saveReminderSettings(booking,true,['1d'],now);const s={...initialSession(),preferences:p,results:rankTrips(p),selectedId:result.trip.id,booked:true,booking,reminderSettings:settings};
    const next=applyResponse(s,processRequest({text:'Запросить ранний заезд',preferences:p,selectedId:result.trip.id}));expect(next.booked).toBe(true);expect(next.booking?.preferences.earlyCheckin).toBe(true);expect(next.reminderSettings?.schedule).toEqual(settings.schedule);
  });
  it('пустые настройки по умолчанию не планируют уведомлений',()=>{expect(initialReminderSettings().enabled).toBe(false);expect(initialReminderSettings().schedule).toEqual([]);});
  it('уточнение роли неоднозначного города не отменяет уже оформленную поездку',()=>{
    const p=preferences(),result=rankTrips(p)[0],booking={id:'booking-1',confirmedAt:now.toISOString(),result,preferences:p,status:'confirmed' as const};
    const s={...initialSession(),preferences:p,results:rankTrips(p),selectedId:result.trip.id,booked:true,booking,reminderSettings:saveReminderSettings(booking,true,['1d'],now)};
    const next=applyResponse(s,processRequest({text:'Антананариву',preferences:p,selectedId:result.trip.id}));
    expect(next.preferences.pendingInput).toBe('Антананариву');expect(next.booked).toBe(true);expect(next.booking?.status).toBe('confirmed');expect(next.reminderSettings?.enabled).toBe(true);
  });
});
