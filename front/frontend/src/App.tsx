import { AnimatePresence } from 'motion/react';
import { useState } from 'react';
import { ArrowRight, Compass, MessageCircle, Route, Sparkles } from 'lucide-react';
import type { AgentAdapter, SlotKey } from './types';
import { useTravelSession } from './state/useTravelSession';
import { Header } from './components/Header';
import { Welcome } from './components/Welcome';
import { Chat } from './components/Chat';
import { Workspace } from './components/Workspace';
import { Modal } from './components/Modal';
import { slotLabels } from './components/Parameters';
import { Booking } from './components/Booking';
import photoCredits from './data/photo-credits.json';

export default function App({ agentAdapter }: { agentAdapter?: AgentAdapter } = {}) {
  const { session, busy, send, reset, activate, select, book, updateDetails, cancelBooking, setReminders, beginBookingEdit } = useTravelSession(agentAdapter);
  const [help, setHelp] = useState(false);
  const [credits, setCredits] = useState(false);
  const [edit, setEdit] = useState<SlotKey>();
  const [editValue, setEditValue] = useState('');
  const [booking, setBooking] = useState(false);
  const [recordMode,setRecordMode] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<'chat' | 'plan'>('plan');
  const working = session.messages.length > 0;
  const selected = session.selectedResult ?? session.results.find(r => r.trip.id === session.selectedId) ?? session.booking?.result;
  const recordConfirmed=recordMode && session.booking?.status==='confirmed';
  const reviewResult=recordConfirmed ? session.booking!.result : selected;
  const reviewPreferences=recordConfirmed ? session.booking!.preferences : session.preferences;
  const sendMessage = (text: string) => { void send(text); };
  const prompts: Record<SlotKey, string> = { when: 'Например: в декабре, летом или 12 декабря', destination: 'Например: в Италию, в Париж или в Европу', origin: 'Например: из Москвы или из Питера', purpose: 'Например: хочу гулять и смотреть архитектуру' };
  return <div className={`app-layout ${working ? 'is-working' : 'is-welcome'}`}><a className="skip-link" href="#main">Перейти к плану поездки</a><Header working={working} hasBooking={!!session.booking} onReset={() => setResetOpen(true)} onHelp={() => setHelp(true)} onTrips={() => { if (selected) { setRecordMode(!!session.booking);setBooking(true); } else if (working) { setMobileTab('plan'); } else { document.getElementById('welcome-message')?.focus(); } }} />
    {!working ? <Welcome onSend={sendMessage} busy={busy} /> : <><div className="mobile-tabs"><button onClick={() => setMobileTab('chat')} aria-pressed={mobileTab === 'chat'}><MessageCircle size={17} />Чат {busy && <span className="mobile-busy" />}</button><button onClick={() => setMobileTab('plan')} aria-pressed={mobileTab === 'plan'}><Compass size={17} />Поездки{session.results.length > 0 && <small>{session.results.length}</small>}</button></div><div className={`app-shell mobile-${mobileTab}`}><Chat messages={session.messages} conflicts={session.conflicts} busy={busy} onSend={sendMessage} /><Workspace session={session} busy={busy} onSend={sendMessage} onEdit={key => { setEdit(key); setEditValue(''); }} onActivate={activate} onSelect={select} onBook={() => {setRecordMode(false);setBooking(true);}} onOpenRecord={()=>{setRecordMode(true);setBooking(true);}} /></div></>}
    <AnimatePresence mode="wait">
    {help && <Modal key="help" title="Одно желание. Целое путешествие." onClose={() => setHelp(false)}><div className="help-steps"><div><Sparkles /><h3>Расскажите о поездке</h3><p>Назовите месяц, город отправления и то, чего хочется. Свободный ввод работает на русском языке.</p></div><div><Compass /><h3>Найдите свой вариант</h3><p>Сравните до пяти поездок: дорога, отель, трансфер и бюджет собраны вместе. У каждого варианта есть объяснение.</p></div><div><Route /><h3>Меняйте планы в диалоге</h3><p>«Хочу подешевле», «с нами собака», «только 5 звёзд» или «на два дня позже». Остальные условия сохранятся.</p></div></div><div className="help-demo"><strong>Это рабочий демонстрационный прототип</strong><p>Ассистент распознаёт ограниченный набор формулировок по правилам. 15 вымышленных поездок, учебные цены и визовые сведения. Реальные бронирования и платежи не выполняются. План, диалог и напоминания сохраняются в этом браузере. При закрытом сайте уведомления не отправляются.</p></div><button className="credits-link" onClick={() => { setHelp(false); setCredits(true); }}>Фотографии и авторы</button><button className="primary-button full-width" onClick={() => setHelp(false)}>Начнём путешествие <ArrowRight size={17} /></button></Modal>}
    {credits && <Modal key="credits" title="Фотографии и авторы" onClose={() => setCredits(false)}><p className="modal-intro">В приложении используются фотографии направлений и атмосферные иллюстрации. Отели вымышленные; снимки не показывают их номера или территорию. Внешний вид фото определяется кадрированием CSS; цвета не изменялись.</p><div className="photo-credits">{photoCredits.map(c => <p key={c.name}><strong>{c.title}</strong><span>{c.author}</span><a href={c.source} target="_blank" rel="noreferrer">Источник</a> · <a href={c.licenseUrl} target="_blank" rel="noreferrer">{c.license}</a></p>)}<p>Остальные фотографии: <a href="https://unsplash.com/license" target="_blank" rel="noreferrer">Unsplash</a>. Мадейра: Colin Watts. Рим: William VanBuskirk. Полный список файлов и источников включён в документацию проекта.</p></div></Modal>}
    {edit && <Modal key="edit" title={slotLabels[edit]} onClose={() => setEdit(undefined)}><p className="modal-intro">Изменится только указанное условие.</p><form className="edit-form" onSubmit={e => { e.preventDefault(); if (editValue.trim()) { void send(editValue,edit); setEdit(undefined); } }}><label htmlFor="edit-slot">Новое условие</label><input id="edit-slot" value={editValue} onChange={e => setEditValue(e.target.value)} placeholder={prompts[edit]} autoFocus required /><button className="primary-button full-width" type="submit">Обновить поездку <ArrowRight size={17} /></button></form></Modal>}
    {booking && reviewResult && <Booking key="booking" result={reviewResult} preferences={reviewPreferences} booked={session.booked && session.booking?.result.trip.id === reviewResult.trip.id} booking={session.booking} reminders={session.reminderSettings} onClose={() => setBooking(false)} onBook={book} onDetailsChange={updateDetails} onRemindersChange={setReminders} onCancel={cancelBooking} onBeginEdit={beginBookingEdit} onUpdate={text => { setBooking(false); sendMessage(text); }} />}
    {resetOpen && <Modal key="reset" title="Начать новую историю?" onClose={() => setResetOpen(false)}><p className="modal-intro">Текущий диалог и план будут сброшены, а напоминания отключены. При желании сначала скачайте выбранную поездку.</p><div className="modal-actions"><button className="secondary-button" onClick={() => setResetOpen(false)}>Остаться в поездке</button><button className="primary-button" onClick={() => { reset(); setResetOpen(false); setBooking(false); }}>Новая поездка <ArrowRight size={17} /></button></div></Modal>}
    </AnimatePresence>
  </div>;
}
