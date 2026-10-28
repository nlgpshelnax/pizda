import { useEffect, useRef } from 'react';
import { useMotionEnabled } from '../motion';
import { ChevronDown } from 'lucide-react';
import type { Preferences, SlotKey } from '../types';
import { money } from '../shared/format';
const slots=[{key:'when' as const,label:'Когда'},{key:'destination' as const,label:'Куда'},{key:'origin' as const,label:'Откуда'},{key:'purpose' as const,label:'Цель'}];
export const slotLabels:Record<SlotKey,string>={when:'Когда поедем?',destination:'Куда отправимся?',origin:'Откуда начнём?',purpose:'Чем займёмся?'};
export function Parameters({preferences:p,onEdit,busy}:{preferences:Preferences;onEdit:(key:SlotKey)=>void;busy:boolean}) {
  const element = useRef<HTMLElement>(null);
  const enabled = useMotionEnabled();
  const previous = useRef<Record<string,string>>({});
  useEffect(() => {
    const next: Record<string,string> = {};
    for(const {key} of slots) {
      next[key] = JSON.stringify(p.slots[key]);
      if(enabled && previous.current[key] && previous.current[key] !== next[key]) element.current?.querySelector(`.parameter-${key}`)?.animate([{backgroundColor:'rgb(200 217 230 / .65)'},{backgroundColor:'transparent'}], {duration:900,easing:'cubic-bezier(.16,1,.3,1)'});
    }
    previous.current=next;
  }, [p, enabled]);
  const shortPurpose = p.unknownPurposes?.length ? p.slots.purpose.value : p.purposes.map((purpose,index)=>{const name=({beach:'Море',culture:'Архитектура',walks:'Прогулки',mountains:'Горы',spa:'SPA'})[purpose];return index===0||purpose==='spa'?name:name.toLowerCase();}).join(', ');
  const wishes=[p.budget?`До ${money(p.budget)}`:'',p.stars?`${p.starsStrict?'Только ':''}${p.stars}★`:'',p.pet?'С питомцем':'',p.visaFree?'Без визы':'',p.central?'В центре':'',p.passport==='RU'?'Паспорт РФ':'',p.privateTransfer?'Индивидуальный трансфер':'',p.earlyCheckin?'Ранний заезд запрошен':''].filter(Boolean);
  return <section ref={element} className="parameters" aria-label="Параметры путешествия"><div className="parameter-grid">{slots.map(({key,label})=>{const slot=p.slots[key];return <button className={`parameter parameter-${slot.status} parameter-${key}`} key={key} onClick={()=>onEdit(key)} disabled={busy}><span className="parameter-top">{label}<ChevronDown size={12} aria-hidden="true"/></span><strong title={slot.value}>{(key==='purpose'?shortPurpose||slot.value:slot.value)||'Нужно уточнить'}</strong><span className={`parameter-status ${slot.status==='YES'&&slot.catalogSupport!=='unsupported'&&slot.resolution!=='unresolved'?'status-confirmed':''}`}>{slot.catalogSupport==='unsupported'?'Сохранено, нет в демо':slot.resolution==='unresolved'?'Сохранено, уточним смысл':slot.status==='YES'?'Уточнено':slot.status==='Vague'?'Примерно':'Не указано'}</span></button>;})}</div>{wishes.length>0&&<div className="wish-list">{wishes.map(w=><span key={w}>{w}</span>)}</div>}</section>;
}
