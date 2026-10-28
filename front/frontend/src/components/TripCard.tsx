import { useState } from 'react';
import { ArrowRight, CalendarDays, CarFront, Check, ChevronDown, Clock3, Coffee, Heart, Hotel, Info, MapPin, PawPrint, Plane, ShieldCheck, Sparkles, Star, Users, Waves, Wifi } from 'lucide-react';
import type { Preferences, RankedTrip } from '../types';
import { money } from '../shared/format';
import { minutes, scheduleProblems } from '../agent/conflicts';
import { destinationZone, flightExample, originZone } from '../agent/itinerary';

export function dateRange(p: Preferences): { start: string; end: string; estimated: boolean } {
  const month = p.month ?? 12;
  const start = p.startDate ?? `${month < 10 ? 2027 : 2026}-${String(month).padStart(2, '0')}-12`;
  const end = new Date(`${start}T12:00:00Z`); end.setUTCDate(end.getUTCDate() + p.nights);
  return { start, end: end.toISOString().slice(0, 10), estimated: !p.startDate };
}
export const shortDate = (date: string) => new Date(`${date}T12:00:00Z`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' }).replace('.', '');
export function visaLabel(p: Preferences, r: RankedTrip) {
  if (p.passport !== 'RU') return 'Виза: нужно уточнить';
  return r.trip.visaForRU === 'free' ? 'Виза не нужна*' : 'Нужна виза*';
}
const at = (value: number) => `${String(Math.floor(value / 60) % 24).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
interface Props { result: RankedTrip; preferences: Preferences; selected: boolean; onSelect: () => void; onBook: () => void; saved: boolean; onSave: () => void; busy: boolean }
export function TripCard({ result: r, preferences: p, selected, onSelect, onBook, saved, onSave, busy }: Props) {
  const t = r.trip; const dates = dateRange(p);
  const timeIssues = scheduleProblems(t);
  return <article className={`trip-card ${selected ? 'trip-selected' : ''}`}>
    <div className="trip-summary">
      <div className="trip-visual"><img src={`/images/${t.image}.jpg`} alt={`Иллюстративное фото: ${t.region}, ${t.country}. Не фотография отеля.`} width="360" height="280" /><span className="illustrative">Фото направления</span><button className={`save-button ${saved ? 'is-saved' : ''}`} aria-label={saved ? 'Убрать из избранного' : 'Сохранить в избранное'} aria-pressed={saved} onClick={onSave}><Heart size={17} fill={saved ? 'currentColor' : 'none'} /></button></div>
      <div className="trip-summary-content"><div className="country-line"><span><MapPin size={12} />{t.city}, {t.country}</span><span className="visa-chip"><ShieldCheck size={12} />{visaLabel(p,r)}</span></div>
        <h3>{t.hotel.name} <span className="hotel-stars" aria-label={`${t.hotel.stars} звезды`}>{t.hotel.stars}<Star size={11} fill="currentColor" /></span></h3>
        <div className="trip-features"><span><CalendarDays />{shortDate(dates.start)} – {shortDate(dates.end)}{dates.estimated && <em>примерно</em>}</span><span>{p.nights} ночей · {p.guests} взр.</span><span><Coffee />Завтраки</span><span><CarFront />Трансфер</span>{t.heatedPool && <span><Waves />Тёплый бассейн</span>}{p.pet && <span><PawPrint />С питомцем</span>}</div>
        <p className="trip-transport"><Plane size={13} />{p.slots.origin.value || 'Город уточняется'} → {t.city} · {t.stop === 'Без пересадок' ? 'без пересадок' : `1 пересадка, ${t.stop}`} · ~{t.flightHours}</p>
        <div className="trip-action"><div className="trip-price"><strong>{money(r.total)}</strong><span>вся поездка · учебная цена</span></div><button className="primary-button" onClick={selected ? onBook : onSelect} disabled={busy || timeIssues.length > 0}>{selected ? 'К оформлению' : 'Выбрать поездку'}<ArrowRight size={15} /></button></div>
      </div>
    </div>
    <div className="trip-main"><CompactRoute result={r} preferences={p} />
      <div className="reasoning"><div><Check size={14} /><p><strong>Почему подходит</strong>{r.reasons[0] || 'Совпадает с указанными условиями.'}</p></div><div><Sparkles size={14} /><p><strong>Компромисс</strong>{r.compromises.length ? r.compromises.join('; ') : 'По известным условиям не нужен.'}</p></div><div><Info size={14} /><p><strong>Риски</strong>{!p.startDate ? 'Даты примерные. ' : ''}Наличие, цена и документы не подтверждены.</p></div></div>
      {timeIssues.length > 0 && <p className="inline-warning">{timeIssues.join(' ')}</p>}
      <div className="trip-details-links"><details><summary>Отель и занятия<ChevronDown size={13} /></summary><p className="hotel-description">{t.hotel.description}</p><p className="detail-amenities"><Wifi size={13} />{t.hotel.amenities.join(' · ')}</p><p className="detail-activities">{t.activities.join(' · ')}</p><p className="visa-explanation">{p.passport === 'RU' ? t.visaNote : 'Для визовых условий укажите гражданство. Правила въезда требуют актуальной проверки.'}</p></details><details><summary>Из чего складывается цена<ChevronDown size={13} /></summary><CostBreakdown result={r} preferences={p} /></details></div>
    </div>
  </article>;
}
export function CompactRoute({result:r,preferences:p,expandable=true,onDetails}:{result:RankedTrip;preferences:Preferences;expandable?:boolean;onDetails?:()=>void}) {
  const [expanded,setExpanded] = useState(false);
  const t=r.trip, dates=dateRange(p), exact=!!p.startDate && !!p.slots.origin.value;
  const flight=flightExample(t,p,dates.start,dates.end);
  const checkin = Math.max(minutes(t.arrival)+60+t.transferMinutes,minutes(t.hotel.checkin));
  const steps = [
    {icon:Plane,label:'Перелёт',value:exact ? flight.departure.time : 'Время уточним',hint:p.slots.origin.value || 'Город уточним'},
    ...(flight.connectionMinutes ? [{icon:Clock3,label:'Пересадка',value:'2 ч',hint:t.stop}] : []),
    {icon:MapPin,label:'Прибытие',value:exact ? t.arrival : 'Время уточним',hint:t.airport},
    {icon:CarFront,label:'Трансфер',value:`${t.transferMinutes} мин`,hint:'После багажа'},
    {icon:Hotel,label:'Заселение',value:exact ? at(checkin) : `От ${t.hotel.checkin}`,hint:shortDate(dates.start)},
    {icon:Plane,label:'Обратно',value:exact ? t.returnDeparture : 'Время уточним',hint:`${shortDate(dates.end)} · выезд ${t.hotel.checkout}`},
  ];
  return <section className="route-preview" aria-label="Основные этапы маршрута"><div className="route-preview-heading"><h3>{p.slots.origin.value || 'Город уточняется'} → {t.airport}</h3><span>{t.flightHours}</span>{onDetails&&<button onClick={onDetails} aria-label={`Полный маршрут и условия: ${t.city}`}>Подробнее<ChevronDown size={12}/></button>}{expandable&&<button onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>{expanded ? 'Свернуть детали' : 'Время и детали'}<ChevronDown size={12} /></button>}</div><ol className="route-stops">{steps.map(s=><li key={s.label}><span className="route-stop-icon"><s.icon size={14} aria-hidden="true"/></span><strong>{s.label}</strong><span>{s.value}</span><small>{s.hint}</small></li>)}</ol>{expanded && <RouteTimeline result={r} preferences={p} />}</section>;
}
export function CostBreakdown({ result: r, preferences: p }: { result: RankedTrip; preferences: Preferences }) {
  return <div className="cost-breakdown"><p>Расчёт за {p.guests} {p.guests === 1 ? 'взрослого' : 'взрослых'}, {p.nights} ночей. Все суммы демонстрационные.</p>{([['transport', 'Дорога туда и обратно', Plane], ['hotel', 'Проживание с завтраками', Hotel], ['transfer', 'Трансферы в обе стороны', CarFront], ['extras', p.pet ? 'Дополнительные расходы и питомец' : 'Дополнительные расходы', WalletIcon]] as const).map(([key, label, Icon]) => <div className="cost-row" key={key}><span><Icon size={16} />{label}</span><strong>{money(r.costs[key])}</strong></div>)}<div className="cost-total"><span>Вся поездка</span><strong>{money(r.total)}</strong></div><p className="muted">Виза, страховка и неуказанные личные покупки не включены. Это предварительный бюджет, не оферта.</p></div>;
}
function WalletIcon({ size = 16 }: { size?: number }) { return <Users size={size} />; }
export function RouteTimeline({ result: r, preferences: p }: { result: RankedTrip; preferences: Preferences }) {
  const t = r.trip; const dates = dateRange(p); const exact = !!p.startDate && !!p.slots.origin.value;
  const flight = flightExample(t, p, dates.start, dates.end);
  const arrival = minutes(t.arrival); const transferStart = arrival + 60; const hotelArrival = transferStart + t.transferMinutes;
  const checkin = Math.max(hotelArrival, minutes(t.hotel.checkin));
  const backAtAirport = minutes(t.hotel.checkout) + t.transferMinutes;
  const stages = [
    { icon: Plane, time: exact ? flight.departure.time : 'Уточняется', title: `${p.slots.origin.value || 'Ваш город'} → ${t.city}`, detail: `${exact ? 'Пример вылета ' + shortDate(flight.departure.date) : 'Предполагаемый перелёт'} · ${t.stop === 'Без пересадок' ? t.stop : 'пересадка: ' + t.stop} · ${p.slots.origin.value ? t.flightHours + ' всего' : 'длительность после уточнения города'}`, tag: `Эконом · ${originZone(p)} · учебный маршрут` },
    ...(flight.connectionMinutes ? [{ icon: ClockIcon, time: exact ? flight.connectionArrival.time : 'Пересадка', title: `Пересадка в Стамбуле · ${flight.connectionMinutes / 60} ч`, detail: exact ? `Прибытие ${flight.connectionArrival.time} · следующий вылет ${flight.connectionDeparture.time}. Время ожидания включено в общую длительность.` : 'Предварительно 2 часа между сегментами. Конкретные рейсы требуют уточнения.', tag: 'Europe/Istanbul · запас на пересадку' }] : []),
    { icon: MapPin, time: exact ? t.arrival : 'После прилёта', title: `Прибытие в ${t.airport}`, detail: '60 мин на паспортный контроль и получение багажа', tag: 'Запас времени заложен в демо' },
    { icon: CarFront, time: exact ? at(transferStart) : '+ 60 мин', title: `${p.privateTransfer ? 'Индивидуальный' : 'Групповой'} трансфер до отеля`, detail: `${t.transferMinutes} мин в пути · прибытие ${exact ? at(hotelArrival) : 'после дороги'}`, tag: 'Включён в стоимость' },
    { icon: Hotel, time: exact ? at(checkin) : `От ${t.hotel.checkin}`, title: `Заселение в ${t.hotel.name}`, detail: `Заселение с ${t.hotel.checkin}; ${p.earlyCheckin ? 'ранний заезд запрошен, но не подтверждён' : 'ранний заезд по согласованию'}`, tag: 'Номер Standard · завтрак' },
    { icon: CompassIcon, time: `${p.nights} ночей`, title: 'Время для вашего путешествия', detail: t.activities.join(' · '), tag: 'Свободная программа' },
    { icon: Hotel, time: t.hotel.checkout, title: `Выезд из отеля · ${shortDate(dates.end)}`, detail: `Трансфер сразу после выезда · ${t.transferMinutes} мин в пути`, tag: 'Местное время' },
    { icon: Plane, time: exact ? t.returnDeparture : 'Уточняется', title: `${t.city} → ${p.slots.origin.value || 'ваш город'}`, detail: `Прибытие в аэропорт ${exact ? at(backAtAirport) : 'предварительно'} · запас перед вылетом ${Math.floor((minutes(t.returnDeparture) - backAtAirport) / 60)} ч ${(minutes(t.returnDeparture) - backAtAirport) % 60} мин. ${exact ? 'Дома ' + shortDate(flight.returnArrival.date) + ' в ' + flight.returnArrival.time + ' (местное время).' : 'Время обратного прибытия уточняется.'}`, tag: `${destinationZone(t)} · обратная дорога включена${flight.connectionMinutes ? ' · пересадка 2 ч' : ''}` },
  ];
  return <div className="route-timeline"><div className="timeline-title"><span><CalendarDays size={15} />{shortDate(dates.start)} – {shortDate(dates.end)}{dates.estimated ? ' · примерно' : ''}</span><span>Местное время</span></div><p className="timeline-notice"><Info size={14} />{exact ? 'Время местное, расписание учебное. Рейсы и наличие мест нужно проверить.' : 'Без точных дат и города расписание ориентировочное. Длительности и запасы показаны по учебным данным.'}</p>{stages.map(s => <div className="timeline-stage" key={s.title}><div className="timeline-time">{s.time}</div><span className="timeline-icon"><s.icon size={16} /></span><div className="timeline-detail"><strong>{s.title}</strong><p>{s.detail}</p></div></div>)}</div>;
}
function ClockIcon({ size = 16 }: { size?: number }) { return <Clock3 size={size} />; }
function CompassIcon({ size = 16 }: { size?: number }) { return <MapPin size={size} />; }
export function CompactTrip({ result: r, preferences, active, onClick, saved }: { result: RankedTrip; preferences: Preferences; active: boolean; onClick: () => void; saved: boolean }) {
  return <button className={`compact-trip ${active ? 'compact-active' : ''}`} onClick={onClick} aria-pressed={active}><div className="compact-image"><img src={`/images/${r.trip.image}.jpg`} alt={`Фото направления: ${r.trip.city}`} width="160" height="160" loading="lazy" />{saved && <span><Heart size={12} fill="currentColor" /></span>}</div><div className="compact-body"><span className="compact-location">{r.trip.city}, {r.trip.country}</span><h3>{r.trip.hotel.name} <small>{r.trip.hotel.stars}★</small></h3><p>{r.compromises[0] || visaLabel(preferences,r).replace('Виза: ', '')}</p><div className="compact-bottom"><strong>{money(r.total)}</strong><ArrowRight size={14} /></div></div></button>;
}
