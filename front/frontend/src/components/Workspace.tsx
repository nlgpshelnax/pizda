import { AnimatePresence, LayoutGroup, motion, useIsPresent } from 'motion/react';
import type { ReactNode } from 'react';
import { timing, easeOut, useMotionEnabled } from '../motion';
import { notify } from './Toast';
import { Fragment, useState } from 'react';
import { ArrowRight, ArrowUpDown, Heart, GitCompareArrows, LoaderCircle } from 'lucide-react';
import type { Session, SlotKey } from '../types';
import { money } from '../shared/format';
import { Parameters } from './Parameters';
import { JourneyCard, CompactJourney, JourneyDetails } from './JourneyCard';
import { visaLabel } from './TripCard';
import { Modal } from './Modal';
import { BookingStatus } from './BookingStatus';
interface Props {session:Session;busy:boolean;onSend:(text:string)=>void;onEdit:(key:SlotKey)=>void;onActivate:(id:string)=>void;onSelect:(id:string)=>void;onBook:()=>void;onOpenRecord:()=>void}
export function Workspace({session:s,busy,onSend,onEdit,onActivate,onSelect,onBook,onOpenRecord}:Props) {
  const enabled=useMotionEnabled();
  const [sort,setSort]=useState('match');
  const [featuredId,setFeaturedId]=useState<string>();
  const [saved,setSaved]=useState<string[]>([]);
  const [onlySaved,setOnlySaved]=useState(false);
  const [compare,setCompare]=useState(false);
  const [detailId,setDetailId]=useState<string>();
  const sorted=[...s.results].sort(sort==='price'?(a,b)=>a.total-b.total:(a,b)=>b.score-a.score||a.total-b.total);
  const ordered=featuredId?[...sorted.filter(r=>r.trip.id===featuredId),...sorted.filter(r=>r.trip.id!==featuredId)]:sorted;
  const shown=onlySaved?ordered.filter(r=>saved.includes(r.trip.id)):ordered;
  const detailed=s.results.find(r=>r.trip.id===detailId);
  const toggleSave=(id:string)=>{const exists=saved.includes(id);setSaved(ids=>ids.includes(id)?ids.filter(i=>i!==id):[...ids,id]);notify(exists?'Поездка удалена из избранного.':'Поездка сохранена.');};
  const openDetails=(id:string)=>{onActivate(id);setDetailId(id);};
  const choose=(id:string)=>{if(shown.findIndex(r=>r.trip.id===id)>=2)setFeaturedId(id);onSelect(id);setDetailId(undefined);onBook();};
  return <main className="workspace" id="main" aria-label="Предложения путешествий" aria-busy={busy}>
    <Parameters preferences={s.preferences} onEdit={onEdit} busy={busy}/>
    <BookingStatus session={s} onOpen={onOpenRecord}/>
    <div className="results-stage"><AnimatePresence initial={false} mode="sync"><ResultLayer key={s.revision} enabled={enabled}>
    {!s.canSearch?<section className="waiting-state"><h1>Уточним поездку в чате</h1><p>{s.preferences.pendingInput?`«${s.preferences.pendingInput}» сохранено. Это направление или город отправления?`:s.preferences.awaitingSlot==='origin'?'Из какого города хотите отправиться?':s.preferences.awaitingSlot==='when'?'Когда поедем? Достаточно месяца или сезона.':'Нужно ещё одно условие. Уже указанные пожелания сохранены.'}</p></section>
    :s.results.length===0?<section className="empty-state"><h1>В демо-каталоге нет совпадения</h1><p>{s.preferences.slots.destination.catalogSupport==='unsupported'?`Направление «${s.preferences.slots.destination.value}» сохранено, но поездок туда нет.`:s.preferences.slots.origin.catalogSupport==='unsupported'?`Город «${s.preferences.slots.origin.value}» сохранён. Маршрута из него в демо нет.`:s.preferences.unknownPurposes?.some(p=>p.strict)?'Обязательная цель сохранена. В каталоге нет предложения, которое её подтверждает.':s.preferences.budget?`Нет подходящей целой поездки до ${money(s.preferences.budget)}. Условия сохранены.`:'Указанные условия сохранены. Измените направление или одно из ограничений в чате.'}</p><div className="empty-actions">{s.preferences.slots.origin.catalogSupport==='unsupported'?<button className="text-link" onClick={()=>onSend('Из Москвы')} disabled={busy}>Рассмотреть вылет из Москвы<ArrowRight size={14}/></button>:<>{s.preferences.budget&&<button className="text-link" onClick={()=>onSend('Без лимита бюджета')} disabled={busy}>Снять лимит бюджета</button>}<button className="text-link" onClick={()=>onSend('Любое направление')} disabled={busy}>Другие направления</button></>}</div></section>
    :<><div className="results-heading"><h1>{shown.length} {shown.length===1?'поездка':shown.length<5&&shown.length>1?'поездки':'поездок'}</h1><div className="results-controls"><button className={`control-button ${onlySaved?'is-active':''}`} onClick={()=>setOnlySaved(!onlySaved)} aria-pressed={onlySaved} aria-label="Показать сохранённые варианты"><Heart size={16} fill={onlySaved?'currentColor':'none'}/>{saved.length>0&&saved.length}</button><button className="control-button compare-button" onClick={()=>setCompare(true)} aria-label="Сравнить поездки"><GitCompareArrows size={16}/><span>Сравнить</span></button><label className="sort-control"><ArrowUpDown size={14} aria-hidden="true"/><select value={sort} onChange={e=>{setFeaturedId(undefined);setSort(e.target.value);}} aria-label="Сортировать поездки"><option value="match">По соответствию</option><option value="price">Сначала дешевле</option></select></label></div>{busy&&<span className="results-updating" role="status"><LoaderCircle size={14} className="spin"/>Обновляем</span>}</div>
      {shown.length===0?<div className="saved-empty"><p>Нет сохранённых поездок. Нажмите на сердечко рядом с предложением.</p><button className="text-link" onClick={()=>setOnlySaved(false)}>Все варианты</button></div>:<><LayoutGroup id={`results-${s.revision}`}><div className="result-grid">{shown.slice(0,5).map((r,index)=><Fragment key={r.trip.id}>{index===2&&<h2 className="alternatives-heading">Ещё {shown.length-2} {shown.length-2===1?'вариант':'варианта'}</h2>}<motion.div className={`motion-card ${index<2?'motion-primary':'motion-compact'}`} key={r.trip.id} layout={enabled} initial={enabled?{opacity:0,y:20}:false} animate={{opacity:1,y:0}} transition={{duration:enabled?timing.card:0,ease:easeOut,delay:enabled?index*.055:0,layout:{duration:enabled?timing.card:0,delay:0}}}>
        {index<2?<JourneyCard result={r} preferences={s.preferences} recommended={r.trip.id===s.results[0]?.trip.id} selected={r.trip.id===s.selectedId} saved={saved.includes(r.trip.id)} busy={busy} onSave={()=>toggleSave(r.trip.id)} onDetails={()=>openDetails(r.trip.id)} onChoose={()=>choose(r.trip.id)}/>:<CompactJourney result={r} onDetails={()=>openDetails(r.trip.id)}/>}
      </motion.div></Fragment>)}</div></LayoutGroup></>}

      <p className="assumptions">{s.preferences.guests} взр.{s.preferences.guestsEstimated?' (предположение)':''}, {s.preferences.nights} ночей{s.preferences.nightsEstimated?' (предположение)':''}. Дорога, отель и трансферы включены. {!s.preferences.startDate?'Даты примерные. ':''}Все цены учебные.</p>
    </>}
    </ResultLayer></AnimatePresence></div>
    <AnimatePresence mode="wait">
    {detailed&&<JourneyDetails key={detailed.trip.id} result={detailed} preferences={s.preferences} busy={busy} saved={saved.includes(detailed.trip.id)} onSave={()=>toggleSave(detailed.trip.id)} onClose={()=>setDetailId(undefined)} onChoose={()=>choose(detailed.trip.id)}/>}
    {compare&&<Modal key="comparison" title="Сравнение поездок" onClose={()=>setCompare(false)} wide><p className="modal-intro">Полные поездки по текущему запросу. Все цены демонстрационные.</p><div className="comparison-list">{ordered.map(r=><section key={r.trip.id}><div><h3>{r.trip.city}, {r.trip.country}</h3><p>{r.trip.hotel.name} {r.trip.hotel.stars}★</p><p>{r.trip.stop==='Без пересадок'?r.trip.stop:`Пересадка: ${r.trip.stop}`}, {r.trip.flightHours}. {visaLabel(s.preferences,r)}</p><p>{r.trip.hotel.pets?'Можно с питомцем. ':''}{r.trip.heatedPool?'Есть подогреваемый бассейн. ':''}{r.compromises.join('; ')||'По указанным условиям компромисса нет.'}</p></div><div><strong>{money(r.total)}</strong><button className="text-link" onClick={()=>{setCompare(false);openDetails(r.trip.id);}}>Подробнее</button></div></section>)}</div></Modal>}
    </AnimatePresence>
  </main>;
}

function ResultLayer({children,enabled}:{children:ReactNode;enabled:boolean}) {
  const present=useIsPresent();
  return <motion.div className="results-layer" data-exiting={!present} inert={!present} aria-hidden={!present||undefined} initial={enabled?{opacity:0}:false} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:enabled?timing.exit:0,ease:easeOut}}>{children}</motion.div>;
}
