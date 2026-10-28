import { useEffect, useRef } from 'react';
import type { Conflict, Message } from '../types';
import { Composer } from './Composer';
import { motion } from 'motion/react';
import { timing, easeOut, useMotionEnabled } from '../motion';
interface Props {messages:Message[];conflicts:Conflict[];busy:boolean;onSend:(text:string)=>void}
export function Chat({messages,conflicts,busy,onSend}:Props) {
  const history=useRef<HTMLDivElement>(null);
  const follow=useRef(true);
  const initialIds=useRef(new Set(messages.map(message=>message.id)));
  const enabled=useMotionEnabled();
  useEffect(()=>{const node=history.current;if(node&&follow.current)node.scrollTo({top:node.scrollHeight,behavior:enabled?'smooth':'instant'});},[messages,busy,conflicts,enabled]);
  return <aside className="chat-panel" aria-label="Диалог о путешествии"><div className="chat-heading"><h2>Ваша поездка</h2></div><div className="chat-history" ref={history} onWheel={e=>{if(e.deltaY<0)follow.current=false;}} onTouchMove={()=>{follow.current=false;}} onKeyDown={e=>{if(['PageUp','Home','ArrowUp'].includes(e.key))follow.current=false;}} onScroll={e=>{const n=e.currentTarget;if(n.scrollHeight-n.scrollTop-n.clientHeight<80)follow.current=true;}} role="log" aria-label="История сообщений" aria-live="polite">{messages.map(m=><motion.div key={m.id} className={`message message-${m.role}`} initial={enabled&&!initialIds.current.has(m.id)?{opacity:0,y:10}:false} animate={{opacity:1,y:0}} transition={{duration:enabled?timing.message:0,ease:easeOut}}><span className="message-author">{m.role==='agent'?'О!дин запрос':'Вы'}</span><p>{m.text}</p></motion.div>)}{busy&&<p className="agent-processing" role="status">Подбираем поездки…</p>}{!busy&&conflicts.length>0&&<div className="conflicts">{conflicts.map(c=><section className={`conflict ${c.hard?'conflict-hard':''}`} key={c.id}><h3>{c.title}</h3><p>{c.description}</p><div className="conflict-actions">{c.alternatives.map(a=><button key={a.label} disabled={busy} onClick={()=>onSend(a.message)}>{a.label}</button>)}</div></section>)}</div>}</div><div className="chat-bottom"><Composer onSend={onSend} busy={busy}/><p className="chat-disclaimer">Демонстрационный подбор. Настоящая бронь и оплата не выполняются.</p></div></aside>;
}
