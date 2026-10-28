import type { PDFFont, PDFPage } from 'pdf-lib';
import type { Preferences, RankedTrip } from '../types';
import { PdfPlanError, preparePdfPlan } from './pdfData';

const MM = 2.8346456693;
const A4: [number, number] = [210 * MM, 297 * MM];
const money = (n: number) => Number.isFinite(n) ? `${new Intl.NumberFormat('ru-RU').format(n)} ₽` : 'Требует уточнения';
const formatDate = (s: string) => new Intl.DateTimeFormat('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',timeZone:'UTC'}).format(new Date(`${s}T12:00:00Z`));

/** Breaks text into measured lines, including exceptionally long unbroken words. */
function linesFor(text: string, font: PDFFont, size: number, width: number): string[] {
  const out: string[] = [];
  let line = '';
  for (const word of text.replace(/\s+/g,' ').trim().split(' ')) {
    if (!word) continue;
    const candidate = line ? `${line} ${word}` : word;
    if (font.widthOfTextAtSize(candidate,size) <= width) { line = candidate; continue; }
    if (line) out.push(line);
    line = '';
    for (const ch of Array.from(word)) {
      if (font.widthOfTextAtSize(line+ch,size) > width && line) { out.push(line); line = ch; }
      else line += ch;
    }
  }
  if (line) out.push(line);
  return out.length ? out : ['Требует уточнения'];
}

export async function createTripPdf(result: RankedTrip, preferences: Preferences, assets?: { regular: Uint8Array; semibold: Uint8Array; prata: Uint8Array }, now = new Date()): Promise<Uint8Array> {
  const plan = preparePdfPlan(result,preferences);
  const [{ PDFDocument, rgb }, { default: fontkit }] = await Promise.all([import('pdf-lib'), import('@pdf-lib/fontkit')]);
  const load = async (path: string) => { const response = await fetch(path); if (!response.ok) throw new PdfPlanError('Не удалось загрузить шрифты PDF. Проверьте соединение и повторите.'); return new Uint8Array(await response.arrayBuffer()); };
  const fonts = assets ?? {regular:await load('/fonts/montserrat-regular.ttf'),semibold:await load('/fonts/montserrat-semibold.ttf'),prata:await load('/fonts/prata-regular.ttf')};
  const document = await PDFDocument.create();
  document.registerFontkit(fontkit);
  const [regular,bold,prata] = await Promise.all([document.embedFont(fonts.regular),document.embedFont(fonts.semibold),document.embedFont(fonts.prata)]);
  const page: PDFPage = document.addPage(A4);
  const navy=rgb(47/255,65/255,86/255), teal=rgb(86/255,124/255,141/255), muted=rgb(77/255,96/255,110/255), line=rgb(200/255,217/255,230/255);
  const W=A4[0], margin=38, right=W-margin, gap=22, column=(W-2*margin-gap)/2;
  const text=(value:string,x:number,y:number,size=9,font=regular,color=navy)=>page.drawText(value,{x,y,size,font,color});
  const rule=(y:number)=>page.drawLine({start:{x:margin,y},end:{x:right,y},thickness:.55,color:line});
  const wrap=(value:string,x:number,y:number,width:number,size=9,font=regular,color=navy,leading=12.2,minY=48) => {
    for (const row of linesFor(value,font,size,width)) { if(y < minY) throw new PdfPlanError('План слишком подробный для одной страницы. Сократите дополнительные пожелания и повторно оформите поездку.'); text(row,x,y,size,font,color); y -= leading; }
    return y;
  };
  const section=(title:string,x:number,y:number)=>{ text(title,x,y,10,bold,navy); return y-16; };
  const list=(items:string[],x:number,y:number,width:number) => {
    for (const item of items) { text('•',x,y,8,regular,teal); y=wrap(item,x+10,y,width-10); y-=3; }
    return y;
  };

  // This is the same typographic wordmark used in the site header: Prata «О!» and the sans-serif «дин запрос».
  text('О!',margin,802,24,prata,teal); text('дин запрос',margin+29,803,15,bold,navy);
  text('Персональный план путешествия',margin,784,8,regular,muted);
  const stamp='Демонстрационный маршрут'; text(stamp,right-bold.widthOfTextAtSize(stamp,8),805,8,bold,navy);
  const generated=`Составлен ${new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'}).format(now)}`;
  text(generated,right-regular.widthOfTextAtSize(generated,8),790,8,regular,muted);
  rule(773);
  let y=751;
  y=wrap(`${plan.origin} → ${plan.destination}`,margin,y,W-2*margin,16,bold,navy,20);
  y=wrap(`${formatDate(plan.start)} – ${formatDate(plan.end)}  ·  ${plan.nights} ночей  ·  ${plan.guests} взр.`,margin,y-2,W-2*margin,9,regular,muted,13);
  y=wrap(`Предварительная стоимость: ${money(plan.total)}`,margin,y-3,W-2*margin,11,bold,navy,15);
  y-=4; rule(y); y-=19;
  const left=margin, second=margin+column+gap;
  let leftY=section('Маршрут',left,y), rightY=section('Проживание',second,y);
  text('Туда',left,leftY,8.5,bold,teal); leftY-=14;
  leftY=list(plan.outbound,left,leftY,column)-2;
  text('Обратно',left,leftY,8.5,bold,teal); leftY-=14;
  leftY=list(plan.inbound,left,leftY,column);
  leftY=wrap('Время местное. Рейсы и расписание учебные и требуют проверки.',left,leftY,column,7.7,regular,muted,10.5);
  rightY=list(plan.hotel,second,rightY,column)-2;
  rightY=section('Стоимость',second,rightY);
  for (const item of plan.costs) {
    const amount=money(item.amount), available=column-bold.widthOfTextAtSize(amount,8.5)-10;
    const labelLines=linesFor(item.label,regular,8.5,available);
    if (rightY<48) throw new PdfPlanError('План слишком подробный для одной страницы. Сократите дополнительные пожелания и повторно оформите поездку.');
    text(amount,second+column-bold.widthOfTextAtSize(amount,8.5),rightY,8.5,bold,navy);
    for (const label of labelLines) { text(label,second,rightY,8.5,regular,navy); rightY-=11.5; }
  }
  rightY-=3; page.drawLine({start:{x:second,y:rightY+6},end:{x:second+column,y:rightY+6},thickness:.5,color:line});
  text('Итого',second,rightY-4,9,bold,navy); const total=money(plan.total); text(total,second+column-bold.widthOfTextAtSize(total,10),rightY-4,10,bold,navy); rightY-=22;
  rightY=wrap('Учебная цена. Виза, страховка и личные расходы не включены.',second,rightY,column,7.7,regular,muted,10.5)-7;
  rightY=section('Чем заняться',second,rightY);
  rightY=list(plan.activities.length ? plan.activities : ['Занятия требуют уточнения'],second,rightY,column);
  y=Math.min(leftY,rightY)-5; rule(y); y-=19;
  y=section('Важная информация',margin,y);
  y=list([...plan.warnings,...plan.advice],margin,y,W-2*margin)-4;
  y=section('Перед путешествием',margin,y);
  const checklist=['Проверить документы и визовые условия','Проверить транспорт и багаж','Подготовить необходимые вещи','Уточнить трансфер и заселение'];
  for (let i=0;i<checklist.length;i++) {
    const cx=margin+(i%2)*(column+gap), cy=y-Math.floor(i/2)*16;
    if(cy<72) throw new PdfPlanError('План слишком подробный для одной страницы. Сократите дополнительные пожелания и повторно оформите поездку.');
    page.drawRectangle({x:cx,y:cy-1,width:8,height:8,borderWidth:.7,borderColor:teal}); text(checklist[i],cx+13,cy,8.2,regular,navy);
  }
  const footer='Демонстрационный план. Не является подтверждением реального бронирования или оплаты. Указанные цены и расписания требуют проверки.';
  rule(55); wrap(footer,margin,42,W-2*margin,7.5,regular,muted,10,20);
  document.setTitle('О!дин запрос — персональный план путешествия');
  document.setSubject('Демонстрационный план поездки');
  return document.save();
}

export async function downloadTripPdf(result: RankedTrip, preferences: Preferences): Promise<void> {
  const bytes = await createTripPdf(result,preferences);
  const blob = new Blob([new Uint8Array(bytes)],{type:'application/pdf'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href=url; link.download=`OdinZapros_TripPlan_${preferences.startDate}.pdf`; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
