import { useRef, useState } from 'react';
import { ArrowUp, LoaderCircle } from 'lucide-react';

interface Props {onSend:(text:string)=>void;busy:boolean;large?:boolean}

export function Composer({onSend,busy,large=false}:Props) {
  const [text,setText]=useState('');
  const [error,setError]=useState(false);
  const input=useRef<HTMLTextAreaElement>(null);
  const id=large?'welcome-message':'chat-message';
  const errorId=`${id}-error`;
  const submit=()=>{
    if(busy)return;
    if(!text.trim()){
      setError(true);
      input.current?.focus();
      return;
    }
    onSend(text);
    setText('');
    setError(false);
  };
  return <form className={`composer ${large?'composer-large':''}`} onSubmit={e=>{e.preventDefault();submit();}}>
    <label htmlFor={id}>{large?'Опишите поездку':'Ваше сообщение'}</label>
    <textarea ref={input} id={id} value={text} maxLength={2000} aria-invalid={error||undefined} aria-describedby={error?errorId:undefined} onChange={e=>{setText(e.target.value);if(error)setError(false);}} placeholder={large?'Например: в июне из Москвы в Европу, хочу прогулки и музеи, до 130 тысяч':'Например: подешевле или с питомцем'} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();submit();}}} rows={large?3:2}/>
    {error&&<p className="composer-error" id={errorId}>Введите сообщение о поездке.</p>}
    <div className="composer-bottom"><span>Enter отправляет, Shift + Enter переносит строку</span><button className="send-button" type="submit" disabled={busy} aria-label="Отправить сообщение">{large && <span>Отправить</span>}{busy?<LoaderCircle size={19} className="spin" aria-hidden="true"/>:<ArrowUp size={20} aria-hidden="true"/>}</button></div>
  </form>;
}
