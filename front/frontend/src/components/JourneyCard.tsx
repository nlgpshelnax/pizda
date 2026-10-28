import { motion } from 'motion/react';
import './journey-polish.css';
import { ChevronRight, Coffee, Heart, ShieldCheck } from 'lucide-react';
import type { Preferences, RankedTrip } from '../types';
import { money } from '../shared/format';
import { scheduleProblems } from '../agent/conflicts';
import { CompactRoute, CostBreakdown, RouteTimeline, dateRange, shortDate, visaLabel } from './TripCard';
import { Modal } from './Modal';

export function matchReason(r: RankedTrip, p: Preferences) {
  const activities = p.purposes.filter(purpose => r.trip.purposes.includes(purpose));
  const names = { beach:'Море и пляжи', culture:'Архитектура', walks:'Прогулки', mountains:'Горы и природа', spa:'SPA' };
  return activities.length ? activities.map((purpose,index) => index===0?names[purpose]:names[purpose].toLowerCase()).slice(0, 2).join(', ') + '.' : r.reasons.find(reason => !reason.startsWith('Занятия:')) || r.reasons[0];
}

export function JourneyFacts({result:r, preferences:p}: {result:RankedTrip;preferences:Preferences}) {
  return <div className="reasoning journey-facts">
    <p><strong>Почему подходит.</strong> {matchReason(r,p)}</p>
    <p><strong>Компромисс.</strong> {r.compromises[0] || 'По указанным условиям не требуется.'}</p>
    <p><strong>Что проверить.</strong> {scheduleProblems(r.trip)[0] || 'Рейсы, наличие и цену.'}</p>
  </div>;
}

interface CardProps {
  result:RankedTrip; preferences:Preferences; recommended:boolean; selected:boolean;
  saved:boolean; busy:boolean; onSave:()=>void; onDetails:()=>void; onChoose:()=>void;
}
export function JourneyCard({result:r,preferences:p,recommended,selected,saved,busy,onSave,onDetails,onChoose}:CardProps) {
  const t=r.trip, dates=dateRange(p), blocked=scheduleProblems(t).length>0;
  return <article className={`trip-card journey-card ${recommended?'journey-recommended':''} ${selected?'trip-selected':''}`} aria-label={`Поездка в ${t.city}`}>
    <div className="journey-country"><span>{t.country}</span>{recommended&&<span className="recommendation">Лучшее по запросу</span>}<button className={`save-button ${saved?'is-saved':''}`} onClick={onSave} aria-label={`${saved?'Убрать из избранного':'Сохранить поездку'}: ${t.city}`} aria-pressed={saved}><Heart size={16} fill={saved?'currentColor':'none'}/></button></div>
    <div className="journey-overview"><button className="journey-photo" onClick={onDetails} aria-label={`Маршрут и условия: ${t.city}`}><motion.img layoutId={`journey-image-${t.id}`} src={`/images/${t.image}.jpg`} alt={`Фото направления: ${t.city}. Не фотография отеля.`} width="112" height="82"/></button><div><motion.h2 layoutId={`journey-title-${t.id}`}>{t.city}</motion.h2><p className="journey-hotel">{t.hotel.name} <span>{t.hotel.stars}★</span></p><p className="journey-dates">{shortDate(dates.start)} - {shortDate(dates.end)}{dates.estimated?' ≈':''}<br/>{p.nights} ночей, {p.guests} взр.</p></div></div>
    <CompactRoute result={r} preferences={p} expandable={false} onDetails={onDetails}/>
    <div className="journey-services"><span><Coffee size={13} aria-hidden="true"/>{t.hotel.meals}</span><span><ShieldCheck size={13} aria-hidden="true"/>{visaLabel(p,r).replace('*','').replace('Виза: нужно уточнить','Виза: уточнить')}</span>{p.privateTransfer&&<span>Инд. трансфер</span>}</div>
    <JourneyFacts result={r} preferences={p}/>
    <div className="journey-bottom"><div className="trip-price"><strong>{money(r.total)}</strong><span>вся поездка</span></div><button className="primary-button choose-trip" onClick={onChoose} disabled={busy||blocked} aria-label={`Выбрать поездку: ${t.city}`}>{selected?'К оформлению':'Выбрать поездку'}</button></div>
  </article>;
}

export function CompactJourney({result:r,onDetails}: {result:RankedTrip;onDetails:()=>void}) {
  const t=r.trip;
  const difference = r.compromises[0] || (t.stop==='Без пересадок'?'Перелёт без пересадок':t.heatedPool?'Подогреваемый бассейн':t.central?'Отель в центре':`${t.flightHours} в пути`);
  return <article className="compact-trip compact-journey"><div className="compact-overview"><motion.img layoutId={`journey-image-${t.id}`} src={`/images/${t.image}.jpg`} alt={`Фото направления: ${t.city}`} width="62" height="54" loading="lazy"/><div><motion.h3 layoutId={`journey-title-${t.id}`}>{t.city}</motion.h3><span>{t.country}</span><p>{t.hotel.name} {t.hotel.stars}★</p></div></div><p className="compact-difference">{difference}</p><div className="compact-bottom"><strong>{money(r.total)}</strong><button onClick={onDetails} aria-label={`Подробнее о поездке: ${t.city}`}>Подробнее<ChevronRight size={13} aria-hidden="true"/></button></div></article>;
}

export function JourneyDetails({result:r,preferences:p,saved,busy,onClose,onSave,onChoose}: {result:RankedTrip;preferences:Preferences;saved:boolean;busy:boolean;onClose:()=>void;onSave:()=>void;onChoose:()=>void}) {
  const dates=dateRange(p);
  return <Modal title={`${r.trip.city}, ${r.trip.country}`} onClose={onClose} wide drawer>
    <div className="detail-trip-header"><img src={`/images/${r.trip.image}.jpg`} alt={`Иллюстративное фото направления: ${r.trip.city}`} width="112" height="78"/><div><h3>{r.trip.hotel.name} <small>{r.trip.hotel.stars}★</small></h3><p>{shortDate(dates.start)} - {shortDate(dates.end)}, {p.nights} ночей, {p.guests} взр.</p><p>{visaLabel(p,r)}. Фото направления, отель вымышленный.</p></div></div>
    <JourneyFacts result={r} preferences={p}/>
    {r.compromises.length>1&&<p className="detail-other-conditions"><strong>Остальные условия:</strong> {r.compromises.slice(1).join('; ')}</p>}
    <div className="detail-choice"><div><strong>{money(r.total)}</strong><span>Дорога, проживание и трансферы</span></div><button className="primary-button" disabled={busy||scheduleProblems(r.trip).length>0} onClick={onChoose}>Выбрать поездку</button></div>
    <p className="detail-demo-note">Цены учебные и не проверяются в реальном времени.</p>
    <RouteTimeline result={r} preferences={p}/>
    <details className="detail-section"><summary>Отель и включённые услуги</summary><p>{r.trip.hotel.description}</p><p>{r.trip.hotel.amenities.join(', ')}</p><p>{r.trip.hotel.meals}. {p.privateTransfer?'Индивидуальный':'Групповой'} трансфер включён.</p></details>
    <details className="detail-section"><summary>Расходы и визовые условия</summary><CostBreakdown result={r} preferences={p}/><p>{p.passport==='RU'?r.trip.visaNote:'Гражданство не указано. Документы для въезда нужно уточнить.'}</p></details>
    <div className="detail-secondary-actions"><button className="text-link" onClick={onSave}><Heart size={15} fill={saved?'currentColor':'none'}/>{saved?'Сохранено в избранном':'Сохранить поездку'}</button></div>
  </Modal>;
}
