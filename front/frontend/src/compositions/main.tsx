import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, ArrowUp, CalendarDays, CarFront, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, Coffee, Heart, Hotel, MapPin, MessageSquare, Plane, Plus, Search, SlidersHorizontal, X } from 'lucide-react';
import type { AgentResponse, Preferences, RankedTrip } from '../types';
import { Brand } from '../components/Header';
import { dateRange, shortDate } from '../components/TripCard';
import { MockAgentAdapter, processRequest } from '../agent/adapter';
import { initialPreferences } from '../state/initial';
import { money } from '../agent/ranking';
import { flightExample } from '../agent/itinerary';
import './preview.css';

// Review-only entry point. Uses the existing agent and catalogue; never writes app storage.
// Design read: preserve brand, flat travel workspace. Variance 3, motion 1, density 8.
const seedText = '12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру. 6 ночей, 1 взрослый, до 130 тысяч.';
const seeded = () => processRequest({text:seedText,preferences:initialPreferences()});
const adapter = new MockAgentAdapter();
const compactMoney = (value:number) => money(value);
type Layout = 'a'|'b';
type MobileView = 'trips'|'route'|'chat';
type ChatMessage = {role:'user'|'agent';text:string};
const labelDate = (date:string) => new Date(`${date}T12:00:00Z`).toLocaleDateString('ru-RU',{day:'numeric',month:'long',timeZone:'UTC'});
const shiftDate = (date:string, days:number) => { const shifted=new Date(`${date}T12:00:00Z`); shifted.setUTCDate(shifted.getUTCDate()+days); return shifted.toISOString().slice(0,10); };
const adults = (count:number) => `${count} ${count===1?'взрослый':'взрослых'}`;
const asTime = (minutes:number) => `${String(Math.floor(minutes/60)%24).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;
const asMinutes = (time:string) => Number(time.slice(0,2))*60+Number(time.slice(3));

function CompositionPreview() {
  const layout:Layout = new URLSearchParams(location.search).get('layout') === 'b' ? 'b' : 'a';
  const [response,setResponse] = useState<AgentResponse>(seeded);
  const [activeId,setActiveId] = useState(seeded().results[0]?.trip.id ?? '');
  const [messages,setMessages] = useState<ChatMessage[]>(()=>[{role:'user',text:seedText},{role:'agent',text:seeded().message}]);
  const [text,setText] = useState('');
  const [busy,setBusy] = useState(false);
  const [saved,setSaved] = useState<string[]>([]);
  const [sort,setSort] = useState('match');
  const [mobileView,setMobileView] = useState<MobileView>(layout==='a'?'trips':'route');
  const [selection,setSelection] = useState<RankedTrip>();
  const [showHelp,setShowHelp] = useState(false);
  const history=useRef<HTMLDivElement>(null);
  const input=useRef<HTMLTextAreaElement>(null);
  const current=response.results.find(r=>r.trip.id===activeId) ?? response.results[0];
  const results=[...response.results].sort(sort==='price'?(a,b)=>a.total-b.total:(a,b)=>b.score-a.score);
  const previewLabel=`Композиция ${layout.toUpperCase()}`;
  useEffect(()=>{if(history.current) history.current.scrollTop=history.current.scrollHeight;},[messages,busy]);
  const send=async(value:string)=>{
    if(!value.trim()||busy)return;
    setMessages(m=>[...m,{role:'user',text:value.trim()}]);setText('');setBusy(true);
    try {
      const next=await adapter.respond({text:value,preferences:response.preferences});
      setResponse(next);setMessages(m=>[...m,{role:'agent',text:next.message}]);
      if(!next.results.some(r=>r.trip.id===activeId))setActiveId(next.results[0]?.trip.id??'');
    } finally {setBusy(false);}
  };
  const reset=()=>{const initial=seeded();setResponse(initial);setActiveId(initial.results[0]?.trip.id ?? '');setMessages([{role:'user',text:seedText},{role:'agent',text:initial.message}]);setSelection(undefined);};
  const activate=(r:RankedTrip)=>{setActiveId(r.trip.id);if(layout==='b')setMobileView('route');};
  const toggleSave=(id:string)=>setSaved(ids=>ids.includes(id)?ids.filter(v=>v!==id):[...ids,id]);
  const chat=<aside className="cp-chat" aria-label="Диалог о путешествии"><div className="cp-panel-title"><h2>Диалог</h2><button className="cp-icon" onClick={()=>input.current?.focus()} aria-label="Написать сообщение"><MessageSquare size={17}/></button></div><div className="cp-chat-history" ref={history} role="log" aria-live="polite">{messages.map((m,i)=><div className={`cp-message cp-message-${m.role}`} key={i}><span>{m.role==='user'?'Вы':'О!дин запрос'}</span><p>{m.text}</p></div>)}{busy&&<p className="cp-processing" role="status">Подбираем варианты…</p>}</div><div className="cp-chat-input"><form onSubmit={e=>{e.preventDefault();void send(text);}}><label htmlFor="cp-message">Изменить пожелания</label><textarea id="cp-message" ref={input} value={text} rows={2} onChange={e=>setText(e.target.value)} placeholder="Например: подешевле" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void send(text);}}}/><div><span>Enter для отправки</span><button className="cp-send" type="submit" disabled={!text.trim()||busy} aria-label="Отправить сообщение"><ArrowUp size={18}/></button></div></form><p>Демо по правилам. Цены и наличие учебные.</p></div></aside>;
  return <div className={`cp-page cp-layout-${layout}`} data-mobile-view={mobileView}>
    <a href="#cp-main" className="cp-skip">Перейти к поездкам</a>
    <header className="cp-header"><a href="/" className="cp-brand" aria-label="Открыть основной сайт"><Brand/></a><nav className="cp-design-switch" aria-label="Композиции рабочего экрана"><span>Композиция</span><a href="?layout=a" aria-current={layout==='a'?'page':undefined}>A</a><a href="?layout=b" aria-current={layout==='b'?'page':undefined}>B</a></nav><div className="cp-header-actions"><span className="cp-demo">Демо</span><button className="cp-help" onClick={()=>setShowHelp(true)}><CircleHelp size={16}/><span>Справка</span></button><button className="cp-new" onClick={reset}><Plus size={16}/><span>Новая поездка</span></button></div></header>
    <nav className="cp-mobile-nav" aria-label="Области экрана">{(['trips',...(layout==='b'?['route']:[]),'chat'] as MobileView[]).map(view=><button key={view} aria-pressed={mobileView===view} onClick={()=>setMobileView(view)}>{view==='trips'?'Поездки':view==='route'?'Маршрут':'Диалог'}</button>)}</nav>
    <div className="cp-workspace">
      {layout==='a'&&chat}
      <main id="cp-main" className="cp-main">
        <SearchStrip preferences={response.preferences} onEdit={()=>{setMobileView('chat');input.current?.focus();}}/>
        {response.conflicts.length>0&&<div className="cp-conflicts">{response.conflicts.map(c=><section key={c.id}><strong>{c.title}</strong><p>{c.description}</p><div>{c.alternatives.map(a=><button key={a.label} onClick={()=>void send(a.message)} disabled={busy}>{a.label}<ArrowRight size={12}/></button>)}</div></section>)}</div>}
        {layout==='a' ? <section className="cp-search-results" aria-label="Предложения поездок"><ResultsHeading count={results.length} sort={sort} onSort={setSort}/>{results.length===0?<EmptyState response={response}/>:<div className="cp-offers">{results.map(r=><Offer key={r.trip.id} result={r} preferences={response.preferences} expanded={r.trip.id===current?.trip.id} saved={saved.includes(r.trip.id)} onOpen={()=>activate(r)} onSave={()=>toggleSave(r.trip.id)} onChoose={()=>setSelection(r)}/>)}</div>}<p className="cp-data-note">В стоимости: дорога туда и обратно, проживание, трансферы и дополнительные расходы. Виза и страховка не включены.</p></section>
        : <div className="cp-planner"><aside className="cp-choices" aria-label="Варианты поездки"><div className="cp-panel-title"><h2>Поездки <span>{results.length}</span></h2><label><SlidersHorizontal size={14}/><select value={sort} onChange={e=>setSort(e.target.value)} aria-label="Сортировка"><option value="match">По запросу</option><option value="price">По цене</option></select></label></div>{results.map(r=><button className={`cp-choice ${r.trip.id===current?.trip.id?'is-active':''}`} key={r.trip.id} onClick={()=>activate(r)} aria-pressed={r.trip.id===current?.trip.id}><img src={`/images/${r.trip.image}.jpg`} alt={`Фото направления ${r.trip.city}`} width="72" height="64"/><span><strong>{r.trip.city}</strong><span>{r.trip.hotel.name} {r.trip.hotel.stars}★</span><b>{compactMoney(r.total)}</b></span><ChevronRight size={15}/></button>)}<p className="cp-choices-note">Цена за {response.preferences.guests} взрослого, {response.preferences.nights} ночей. Все предложения демонстрационные.</p></aside><section className="cp-route-workspace" aria-label="Подробности выбранной поездки">{current?<Planner result={current} preferences={response.preferences} saved={saved.includes(current.trip.id)} onSave={()=>toggleSave(current.trip.id)} onChoose={()=>setSelection(current)}/>:<EmptyState response={response}/>}</section></div>}
      </main>
      {layout==='b'&&chat}
    </div>
    {(selection||showHelp)&&<PreviewDialog title={selection?'Поездка выбрана':previewLabel} onClose={()=>{setSelection(undefined);setShowHelp(false);}}>{selection?<><p><strong>{selection.trip.city}, {selection.trip.hotel.name}</strong></p><p>{compactMoney(selection.total)} за всю поездку.</p><p>Это интерактивный предпросмотр композиции. Оформление и напоминания доступны в основном приложении и сохранятся после выбора дизайна.</p><a className="cp-primary" href="/">Открыть основной сайт<ArrowRight size={15}/></a></>:<><p>Сравниваем две композиции на одном запросе и данных существующего каталога.</p><p>A помогает сравнивать предложения списком. B держит подробный маршрут рядом с вариантами и диалогом.</p><p>Можно переключить поездку, раскрыть расходы и изменить запрос. Предпросмотр не меняет сохранённую поездку в основном приложении.</p></>}</PreviewDialog>}
  </div>;
}

function SearchStrip({preferences:p,onEdit}:{preferences:Preferences;onEdit:()=>void}) {
  const dates=dateRange(p);
  return <section className="cp-search-strip" aria-label="Параметры поездки"><div className="cp-search-caption"><Search size={16}/><span>Параметры поездки</span><button onClick={onEdit}>Изменить</button></div><div className="cp-search-values"><div><span>Откуда</span><strong>{p.slots.origin.value||'Не указано'}</strong></div><div><span>Куда</span><strong>{p.slots.destination.value||'Не указано'}</strong></div><div><span>Когда</span><strong>{shortDate(dates.start)} - {shortDate(dates.end)} {dates.start.slice(0,4)}</strong></div><div><span>Кто едет</span><strong>{adults(p.guests)}</strong></div><div><span>Бюджет</span><strong>{p.budget?`до ${compactMoney(p.budget)}`:'Без лимита'}</strong></div></div><p className="cp-mobile-conditions">{adults(p.guests)} · {p.budget?`до ${compactMoney(p.budget)}`:'Бюджет без лимита'}</p><p className="cp-purpose"><span>{p.slots.purpose.value||'Цель пока не указана'}</span><span className="cp-param-count"><Check size={12}/>{Object.values(p.slots).filter(slot=>slot.status!=='NO').length} из 4 параметров</span></p></section>;
}
function ResultsHeading({count,sort,onSort}:{count:number;sort:string;onSort:(v:string)=>void}) {
  return <div className="cp-results-heading"><h1>{count} {count===1?'вариант':count>1&&count<5?'варианта':'вариантов'} поездки</h1><label>Сортировать<select value={sort} onChange={e=>onSort(e.target.value)} aria-label="Сортировать предложения"><option value="match">По соответствию</option><option value="price">Сначала дешевле</option></select></label></div>;
}
function Offer({result:r,preferences:p,expanded,saved,onOpen,onSave,onChoose}:{result:RankedTrip;preferences:Preferences;expanded:boolean;saved:boolean;onOpen:()=>void;onSave:()=>void;onChoose:()=>void}) {
  const t=r.trip, dates=dateRange(p);
  const [costsOpen,setCostsOpen]=useState(false);
  return <article className={`cp-offer ${expanded?'is-expanded':''}`}><div className="cp-offer-top"><button className="cp-offer-image" onClick={onOpen} aria-label={`Показать ${t.city}`}><img src={`/images/${t.image}.jpg`} alt={`Фото направления ${t.city}`} width="112" height="86"/></button><div className="cp-offer-title"><button onClick={onOpen}><span>{t.city}, {t.country}</span><h2>{t.hotel.name}<small>{t.hotel.stars}★</small></h2></button><p>{shortDate(dates.start)} - {shortDate(dates.end)}, {p.nights} ночей</p><div className="cp-offer-services"><span><Coffee size={12}/>Завтраки</span><span><CarFront size={12}/>Трансфер</span></div></div><div className="cp-transport"><span>{p.slots.origin.value||'Откуда'} → {t.airport}</span><strong>{t.stop==='Без пересадок'?'Без пересадок':`Через ${t.stop}`}</strong><p>{t.flightHours} в пути</p></div><div className="cp-offer-price"><strong>{compactMoney(r.total)}</strong><span>вся поездка</span>{expanded?<button className="cp-primary" onClick={onChoose}>Выбрать<ArrowRight size={14}/></button>:<button className="cp-open" onClick={onOpen}>Посмотреть<ChevronRight size={14}/></button>}</div><button className={`cp-favourite ${saved?'is-saved':''}`} onClick={onSave} aria-label={saved?'Убрать из избранного':'Сохранить поездку'} aria-pressed={saved}><Heart size={17} fill={saved?'currentColor':'none'}/></button></div>
    {expanded&&<div className="cp-offer-expanded"><div className="cp-selected-heading"><span>Маршрут поездки</span><span>Виза: нужно уточнить</span></div><CompactPath result={r} preferences={p}/><Facts result={r} preferences={p}/><button className="cp-disclosure" onClick={()=>setCostsOpen(!costsOpen)} aria-expanded={costsOpen}>Расходы и условия<ChevronDown size={13}/></button>{costsOpen&&<CostList result={r}/>}</div>}
    {!expanded&&r.compromises.length>0&&<p className="cp-row-compromise">Компромисс: {r.compromises[0]}</p>}
  </article>;
}
function CompactPath({result:r,preferences:p}:{result:RankedTrip;preferences:Preferences}) {
  const d=dateRange(p), t=r.trip, f=flightExample(t,p,d.start,d.end);
  const hotelTime=asTime(Math.max(asMinutes(t.arrival)+60+t.transferMinutes,asMinutes(t.hotel.checkin)));
  const steps=[{icon:Plane,title:'Вылет',time:f.departure.time,note:p.slots.origin.value},...(f.connectionMinutes?[{icon:Clock3,title:'Пересадка',time:'2 ч',note:t.stop}]:[]),{icon:CarFront,title:'Трансфер',time:`${t.transferMinutes} мин`,note:'После багажа'},{icon:Hotel,title:'Заселение',time:hotelTime,note:labelDate(d.start)},{icon:Plane,title:'Обратно',time:t.returnDeparture,note:labelDate(d.end)}];
  return <ol className="cp-compact-path">{steps.map(s=><li key={s.title}><s.icon size={15}/><span>{s.title}</span><strong>{s.time}</strong><small>{s.note}</small></li>)}</ol>;
}
function Facts({result:r,preferences:p}:{result:RankedTrip;preferences:Preferences}) {
  return <dl className="cp-facts"><div><dt>Подходит</dt><dd>{r.trip.central?'Отель в центре, рядом прогулочные маршруты.':r.reasons[0]||'Соответствует известным условиям.'}</dd></div><div><dt>Компромисс</dt><dd>{r.compromises[0]||(r.trip.stop==='Без пересадок'?'По известным условиям не требуется.':`Перелёт с пересадкой в Стамбуле.`)}</dd></div><div><dt>Уточнить</dt><dd>{!p.startDate?'Точные даты, ':''}виза, наличие номера и итоговая цена.</dd></div></dl>;
}
function CostList({result:r}:{result:RankedTrip}) {
  return <dl className="cp-cost-list">{([['Дорога',r.costs.transport],['Отель',r.costs.hotel],['Трансферы',r.costs.transfer],['Прочее',r.costs.extras]] as const).map(([label,cost])=><div key={label}><dt>{label}</dt><dd>{compactMoney(cost)}</dd></div>)}</dl>;
}
function Planner({result:r,preferences:p,saved,onSave,onChoose}:{result:RankedTrip;preferences:Preferences;saved:boolean;onSave:()=>void;onChoose:()=>void}) {
  const d=dateRange(p), t=r.trip, f=flightExample(t,p,d.start,d.end);
  const [details,setDetails]=useState(false);
  const arrivalMins=asMinutes(t.arrival),transferStart=arrivalMins+60,checkin=Math.max(transferStart+t.transferMinutes,asMinutes(t.hotel.checkin));
  return <><div className="cp-route-heading"><div><h1>{t.city}</h1><p>{labelDate(d.start)} - {labelDate(d.end)}, {p.nights} ночей</p></div><button className={`cp-favourite ${saved?'is-saved':''}`} onClick={onSave} aria-label={saved?'Убрать из избранного':'Сохранить поездку'} aria-pressed={saved}><Heart size={18} fill={saved?'currentColor':'none'}/></button></div><div className="cp-plan-scroll"><div className="cp-day"><CalendarDays size={15}/><h2>{labelDate(d.start)}</h2><span>Дорога и заселение</span></div><ol className="cp-itinerary"><li><time>{f.departure.time}</time><span className="cp-stop-icon"><Plane size={15}/></span><div><h3>{p.slots.origin.value} → {t.airport}</h3><p>{t.flightHours} в пути{f.connectionMinutes?', включая пересадку':''}</p>{!!f.connectionMinutes&&<div className="cp-connection"><span>Стамбул</span><strong>{f.connectionArrival.time} - {f.connectionDeparture.time}</strong><span>2 ч на пересадку</span></div>}</div></li><li><time>{t.arrival}</time><span className="cp-stop-icon"><MapPin size={15}/></span><div><h3>Прибытие в {t.airport}</h3><p>60 минут на контроль и получение багажа</p></div></li><li><time>{asTime(transferStart)}</time><span className="cp-stop-icon"><CarFront size={15}/></span><div><h3>Трансфер до отеля</h3><p>{t.transferMinutes} минут, включён в стоимость</p></div></li><li className="cp-hotel-stop"><time>{asTime(checkin)}</time><span className="cp-stop-icon"><Hotel size={15}/></span><div><h3>{t.hotel.name} <small>{t.hotel.stars}★</small></h3><p>Заселение, {p.nights} ночей, завтраки</p><div className="cp-hotel-inline"><img src={`/images/${t.image}.jpg`} alt={`Направление: ${t.city}. Иллюстративное фото, не изображение отеля.`} width="112" height="72"/><p>{t.hotel.description}<span>На фото {t.city}, не отель.</span></p></div></div></li></ol>{p.nights>1&&<div className="cp-stay-days"><span>{labelDate(shiftDate(d.start,1))}{p.nights>2?` - ${labelDate(shiftDate(d.end,-1))}`:''}</span><strong>Свободные дни</strong><p>{t.activities.join(', ')}</p></div>}<div className="cp-day cp-return-day"><CalendarDays size={15}/><h2>{labelDate(d.end)}</h2><span>Возвращение</span></div><div className="cp-return-route"><span><b>{t.hotel.checkout}</b>Выезд</span><ArrowRight size={13}/><span><b>{t.returnDeparture}</b>{t.airport}</span><ArrowRight size={13}/><span><b>{f.returnArrival.time}</b>{p.slots.origin.value}</span></div><Facts result={r} preferences={p}/><button className="cp-disclosure" onClick={()=>setDetails(!details)} aria-expanded={details}>Расходы и визовые условия<ChevronDown size={13}/></button>{details&&<><CostList result={r}/><p className="cp-small-note">Гражданство не указано. Для въезда нужно уточнить документы. Все сведения демонстрационные.</p></>}</div><footer className="cp-plan-footer"><div><strong>{compactMoney(r.total)}</strong><span>вся поездка за {p.guests} взрослого</span></div><button className="cp-primary" onClick={onChoose}>Выбрать поездку<ArrowRight size={15}/></button></footer></>;
}
function EmptyState({response}:{response:AgentResponse}) {return <div className="cp-empty"><h2>{response.canSearch?'В каталоге нет совпадений':'Нужна ещё одна деталь'}</h2><p>{response.message}</p></div>;}
function PreviewDialog({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{ref.current?.showModal();return()=>ref.current?.close();},[]);
  return <dialog className="cp-dialog" ref={ref} aria-label={title} onCancel={e=>{e.preventDefault();onClose();}}><div><h2>{title}</h2><button className="cp-icon" onClick={onClose} aria-label="Закрыть"><X size={19}/></button></div>{children}</dialog>;
}

createRoot(document.getElementById('composition-root')!).render(<StrictMode><CompositionPreview/></StrictMode>);
