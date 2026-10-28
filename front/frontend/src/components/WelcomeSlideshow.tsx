import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react';
import credits from '../data/photo-credits.json';
import './welcome-slideshow.css';

const slides = [
  {image:'coast', title:'Манарола, Чинкве-Терре', region:'Лигурия, Италия', author:'Jack Ward', source:'https://unsplash.com/photos/manarola-italy-rknrvCrfS1k', license:'Unsplash', position:'50% 58%'},
  ...['florence','crete','kotor'].map((image, i) => ({...credits.find(c=>c.name===image)!, image, title:['Флоренция','Ханья, Крит','Котор'][i], region:['Тоскана, Италия','Греция','Черногория'][i], position:'50% 50%'})),
  {image:'madeira', title:'Мадейра', region:'Португалия', author:'Colin Watts', source:'https://unsplash.com/photos/C8e3LGjg3fc', license:'Unsplash', position:'50% 50%'},
];
const src = (index:number) => `/images/welcome/${slides[index].image}.webp`;

export function WelcomeSlideshow() {
  const [index,setIndex]=useState(0);
  const [previous,setPrevious]=useState<number>();
  const [direction,setDirection]=useState(1);
  const [paused,setPaused]=useState(false);
  const [hover,setHover]=useState(false);
  const [focused,setFocused]=useState(false);
  const [hidden,setHidden]=useState(document.hidden);
  const [reduced,setReduced]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [loading,setLoading]=useState(false);
  const [revision,setRevision]=useState(0);
  const [error,setError]=useState('');
  const lock=useRef(false);
  const mounted=useRef(true);
  useEffect(()=>{ mounted.current=true; const media=matchMedia('(prefers-reduced-motion: reduce)'); const visibility=()=>setHidden(document.hidden); const motion=()=>setReduced(media.matches); document.addEventListener('visibilitychange',visibility);media.addEventListener('change',motion); return()=>{mounted.current=false;document.removeEventListener('visibilitychange',visibility);media.removeEventListener('change',motion);}; },[]);
  const change=async(next:number, step=1, automatic=false)=>{
    if(lock.current)return;
    setRevision(r=>r+1);
    if(next===index)return;
    lock.current=true;setLoading(true);setError('');
    try {
      const img=new Image();img.src=src(next);await img.decode();
      if(!mounted.current)return;
      if(automatic&&(document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches))return;
      setDirection(step);setPrevious(reduced?undefined:index);setIndex(next);
    } catch {if(mounted.current)setError('Фото не загрузилось. Попробуйте переключить ещё раз.');}
    finally {lock.current=false;if(mounted.current)setLoading(false);}
  };
  useEffect(()=>{
    if(paused||hover||focused||hidden||reduced||loading)return;
    const timer=window.setTimeout(()=>void change((index+1)%slides.length,1,true),15000);
    return()=>clearTimeout(timer);
  },[index,revision,paused,hover,focused,hidden,reduced,loading]);
  useEffect(()=>{if(previous===undefined)return;const timer=window.setTimeout(()=>setPrevious(undefined),750);return()=>clearTimeout(timer);},[previous,index]);
  const current=slides[index];
  return <figure className="welcome-photo welcome-slideshow" aria-label="Направления для вдохновения" aria-roledescription="карусель" onMouseEnter={()=>setHover(true)} onMouseLeave={()=>setHover(false)} onFocusCapture={()=>setFocused(true)} onBlurCapture={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setFocused(false);}}>
    <div className={`welcome-photo-frame ${previous!==undefined?'is-sliding':''} ${direction<0?'slide-back':''}`}>
      {previous!==undefined&&<img className="slide-out" src={src(previous)} alt="" aria-hidden="true" style={{objectPosition:slides[previous].position}}/>}
      <img key={index} className="slide-current" src={src(index)} alt={`${current.title}, ${current.region}`} width="1200" height="1500" fetchPriority={index===0?'high':'auto'} style={{objectPosition:current.position}}/>
      <div className="slide-caption"><strong>{current.title}</strong><span>{current.region}</span></div>
      <div className="slide-arrows"><button type="button" disabled={loading||previous!==undefined} onClick={()=>void change((index+slides.length-1)%slides.length,-1)} aria-label="Предыдущее фото"><ChevronLeft size={20}/></button><button type="button" disabled={loading||previous!==undefined} onClick={()=>void change((index+1)%slides.length)} aria-label="Следующее фото"><ChevronRight size={20}/></button></div>
    </div>
    <figcaption><div className="slide-controls"><div className="slide-dots" aria-label="Выбор фотографии">{slides.map((s,i)=><button key={s.image} type="button" aria-label={`Фото ${i+1}: ${s.title}`} aria-current={i===index?'true':undefined} disabled={loading||previous!==undefined} onClick={()=>void change(i,i<index?-1:1)}><span/></button>)}</div><button className="slide-pause" type="button" onClick={()=>setPaused(p=>!p)} disabled={reduced} aria-label={reduced?'Автосмена отключена: уменьшение движения':paused?'Включить автосмену фото':'Приостановить автосмену фото'}>{paused||reduced?<Play size={15}/>:<Pause size={15}/>}</button></div><a href={current.source} target="_blank" rel="noreferrer">Фото: {current.author} · {current.license}</a></figcaption>
    <span className="visually-hidden" aria-live={paused||focused?'polite':'off'}>{index+1} из {slides.length}: {current.title}, {current.region}</span>
    {error&&<p role="status" className="slide-error">{error}</p>}
  </figure>;
}
