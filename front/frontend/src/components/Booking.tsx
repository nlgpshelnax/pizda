import { AnimatePresence } from 'motion/react';
import { notify } from './Toast';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCheck, Download, Info, ShieldCheck } from 'lucide-react';
import type { Preferences, RankedTrip } from '../types';
import { Modal } from './Modal';
import { CompactRoute, CostBreakdown, dateRange, shortDate, visaLabel } from './TripCard';
import { bookingBlockers, supportedOrigins, todayInMoscow, validateBookingFields } from '../booking/review';
import type { BookingDetailsPatch, BookingFields } from '../booking/review';
import { TripReminders } from './TripReminders';
import { DateField } from './DateField';
import { initialReminderSettings } from '../reminders/model';
import type { ReminderSettings } from '../reminders/model';
import type { Session } from '../types';
import { money } from '../shared/format';
import { downloadTripPdf } from '../booking/tripPdf';
import { PdfPlanError } from '../booking/pdfData';

interface Props {
  result: RankedTrip; preferences: Preferences; booked: boolean; booking?: Session['booking']; reminders?: ReminderSettings;
  onClose: () => void; onBook: () => void; onUpdate: (text:string) => void;
  onDetailsChange: (patch:BookingDetailsPatch) => void; onRemindersChange:(settings:ReminderSettings)=>void; onCancel:()=>void | Promise<void>; onBeginEdit:()=>void;
}
export function Booking({result:r,preferences:p,booked,booking,reminders,onClose,onBook,onUpdate,onDetailsChange,onRemindersChange,onCancel,onBeginEdit}:Props) {
  const [fields,setFields] = useState<BookingFields>({date:p.startDate ?? '',guests:String(p.guests),origin:p.slots.origin.value});
  const [accepted,setAccepted] = useState(false);
  const [editingBooked,setEditingBooked] = useState(false);
  const [cancelConfirm,setCancelConfirm] = useState(false);
  const [cancelSuccess,setCancelSuccess] = useState(false);
  const [cancelBusy,setCancelBusy] = useState(false);
  const [cancelError,setCancelError] = useState('');
  const cancelling = useRef(false);
  const confirmCancel = async () => {
    if(cancelling.current)return;
    cancelling.current=true;setCancelBusy(true);setCancelError('');
    try {await onCancel();setCancelConfirm(false);setCancelSuccess(true);}
    catch {setCancelError('Не удалось отменить поездку. Попробуйте ещё раз.');}
    finally {cancelling.current=false;setCancelBusy(false);}
  };
  const [submitError,setSubmitError] = useState('');
  const [pdfError,setPdfError] = useState('');
  const [pdfBusy,setPdfBusy] = useState(false);
  const downloadPdf = async () => {
    if (!confirmed || !booking || pdfBusy) return;
    setPdfError(''); setPdfBusy(true);
    try { await downloadTripPdf(booking.result,booking.preferences); notify('План PDF подготовлен и передан браузеру для скачивания.'); }
    catch (error) { const message=error instanceof PdfPlanError ? error.message : 'Не удалось создать PDF. Проверьте соединение и попробуйте ещё раз.';setPdfError(message);notify(message,true); }
    finally { setPdfBusy(false); }
  };
  useEffect(()=>{ if(!booked && p.guestsEstimated) onDetailsChange({guests:p.guests,guestsEstimated:false}); },[]);
  const errors=validateBookingFields(fields);
  const invalid=Object.keys(errors).length>0;
  const blockers=bookingBlockers(r,p);
  const unacceptedPool=r.compromises.some(c=>c.includes('бассейн')&&!c.includes('согласовано'));
  const change=(key:keyof BookingFields,value:string)=>{
    const next={...fields,[key]:value};setFields(next);setSubmitError('');
    const localErrors=validateBookingFields(next);
    if(key==='date' && !localErrors.date) onDetailsChange({startDate:value});
    if(key==='guests' && !localErrors.guests) onDetailsChange({guests:Number(value),guestsEstimated:false});
    if(key==='origin') onDetailsChange({origin:value});
  };
  const submit=()=>{
    if(invalid || blockers.length || unacceptedPool || !accepted) {setSubmitError('Проверьте выделенные условия и подтвердите демонстрационный характер поездки.');return;}
    onBook();setEditingBooked(false);
  };
  const confirmed=booked && !editingBooked && booking?.status==='confirmed';
  return <><Modal title={confirmed ? 'Ваша демо-поездка' : 'Детали поездки'} onClose={onClose} wide>
    {confirmed ? <>
      <div className="booking-confirmed"><CheckCheck size={21}/><div><strong>Демо-поездка оформлена</strong><p>Оплаты и настоящего бронирования не было.</p></div></div>
      <BookingSummary result={booking.result} preferences={booking.preferences}/>
      <div className="confirmed-plan-total"><span>Вся поездка · {booking.preferences.guests} взр.</span><strong>{money(booking.result.total)}</strong></div>
      <TripReminders booking={booking} settings={reminders ?? initialReminderSettings()} onChange={onRemindersChange} active />
      <div className="post-booking"><h3>Управление поездкой</h3><div className="post-booking-actions"><button onClick={()=>{onBeginEdit();setFields({date:booking.preferences.startDate??'',guests:String(booking.preferences.guests),origin:booking.preferences.slots.origin.value});setEditingBooked(true);}}>Изменить даты и гостей<ArrowRight size={14}/></button><button onClick={()=>onUpdate('Запросить ранний заезд')}>{p.earlyCheckin ? 'Ранний заезд запрошен' : 'Запросить ранний заезд'}<ArrowRight size={14}/></button><button onClick={()=>onUpdate(p.privateTransfer ? 'Обычный трансфер' : 'Добавить индивидуальный трансфер')}>{p.privateTransfer ? 'Вернуть обычный трансфер' : 'Индивидуальный трансфер +3 500 ₽'}<ArrowRight size={14}/></button><button onClick={()=>onUpdate('Давай на два дня позже')}>Перенести на два дня позже<ArrowRight size={14}/></button></div></div>
      <div className="booking-bottom-links"><button className="text-link" disabled={pdfBusy} onClick={()=>void downloadPdf()}><Download size={14}/>{pdfBusy?'Создаём PDF…':'Скачать план PDF'}</button><button className="cancel-booking-link" onClick={()=>setCancelConfirm(!cancelConfirm)}>Отменить демо-бронирование</button></div>
      {pdfError && <p className="form-error" role="alert">{pdfError}</p>}
    </> : <>
      {booking?.status==='cancelled' && <p className="booking-estimate">Демо-бронирование отменено. Напоминания на сайте выключены. Событие, ранее добавленное в календарь, нужно удалить вручную.</p>}
      {booking?.status==='needs-confirmation' && <p className="booking-estimate"><Info size={14}/>План изменён. Прежние напоминания отключены до нового оформления.</p>}
      <BookingSummary result={r} preferences={p}/>
      <form onSubmit={e=>{e.preventDefault();submit();}} noValidate>
        <div className="booking-form"><DateField value={fields.date} min={todayInMoscow()} error={errors.date} onChange={value=>change('date',value)}/><label>Взрослые<input aria-label="Взрослые" type="number" value={fields.guests} min={1} max={6} onChange={e=>change('guests',e.target.value)} aria-invalid={!!errors.guests} aria-describedby="booking-guests-error" required/>{errors.guests && <small className="field-error" id="booking-guests-error">{errors.guests}</small>}</label><label className="origin-field">Откуда<input aria-label="Откуда" list="booking-origins" value={fields.origin} onChange={e=>change('origin',e.target.value)} aria-invalid={!!errors.origin} aria-describedby="booking-origin-error" autoComplete="off" required/><datalist id="booking-origins">{supportedOrigins.map(city=><option key={city} value={city}/>)}</datalist>{errors.origin && <small className="field-error" id="booking-origin-error">{errors.origin}</small>}</label></div>
        <div className="booking-live-total" aria-live="polite"><span>{invalid ? 'Уточните поля для расчёта' : 'Вся поездка'}</span>{!invalid && <strong>{money(r.total)}</strong>}</div>
        {!invalid && <CompactRoute result={r} preferences={p}/>}
        {blockers.filter(message=>!Object.values(errors).includes(message)).map(message=><p className="field-error booking-blocker" key={message}>{message}</p>)}
        <details className="booking-cost-details"><summary>Расходы и визовые условия</summary><CostBreakdown result={r} preferences={p}/><p className="booking-visa"><ShieldCheck size={14}/>{visaLabel(p,r)}. {p.passport==='RU' ? r.trip.visaNote : 'Гражданство пока не указано. Условия въезда нужно уточнить.'}</p></details>
        <p className="booking-compact-risk"><strong>Компромисс:</strong> {r.compromises.join('; ')||'По известным условиям не требуется.'}<br/><strong>Риски:</strong> наличие номеров, рейсы и цены не подтверждены.</p>
        {unacceptedPool && <button type="button" className="secondary-button full-width" onClick={()=>onUpdate('Согласен на подогреваемый бассейн вместо моря')}>Согласен на подогреваемый бассейн</button>}
        <label className="checkbox-label"><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>Понимаю, что настоящая бронь не создаётся и оплаты не будет. Учитываю указанные риски и компромиссы.</label>
        {submitError && <p className="form-error" role="alert">{submitError}</p>}
        <div className="booking-submit"><button className="primary-button full-width" type="submit" disabled={invalid||blockers.length>0||unacceptedPool||!accepted}>Оформить демо-поездку<ArrowRight size={16}/></button></div>
      </form>
    </>}
  </Modal>
  <AnimatePresence mode="wait">
  {cancelConfirm&&<Modal key="cancel-confirm" title="Отменить поездку?" onClose={()=>{if(!cancelBusy)setCancelConfirm(false);}}><p>Вы действительно хотите отменить демонстрационное бронирование?</p><p className="cancel-note">Напоминания на сайте отключатся. Скачанное событие нужно удалить из календаря вручную.</p>{cancelError&&<p role="alert" className="form-error">{cancelError}</p>}<div className="modal-actions"><button type="button" className="secondary-button" disabled={cancelBusy} data-modal-autofocus onClick={()=>setCancelConfirm(false)}>Оставить поездку</button><button type="button" className="primary-button cancel-confirm-button" disabled={cancelBusy} onClick={()=>void confirmCancel()}>{cancelBusy?'Отменяем…':'Да, отменить'}</button></div></Modal>}
  {cancelSuccess&&<Modal key="cancel-success" title="Бронирование отменено" onClose={()=>{setCancelSuccess(false);onClose();}}><p role="status">Демонстрационная поездка отменена. Вы можете выбрать другой вариант.</p><button type="button" className="primary-button full-width cancel-success-close" onClick={()=>{setCancelSuccess(false);onClose();}}>Вернуться к вариантам</button></Modal>}
  </AnimatePresence>
  </>;
}
function BookingSummary({result:r,preferences:p}:{result:RankedTrip;preferences:Preferences}) {
  const dates=dateRange(p);
  return <div className="booking-summary"><img src={`/images/${r.trip.image}.jpg`} alt={`Иллюстрация направления: ${r.trip.city}`} width="90" height="72"/><div><span>{r.trip.city}, {r.trip.country}</span><h3>{r.trip.hotel.name} <small>{r.trip.hotel.stars}★</small></h3><p>{shortDate(dates.start)} – {shortDate(dates.end)} · {p.nights} ночей{dates.estimated ? ' · примерно' : ''}</p></div></div>;
}
