import { describe, it, expect } from 'vitest';
import { readFile } from 'node:fs/promises';
import { PDFDocument } from 'pdf-lib';
import { trips } from '../src/data/trips';
import { initialPreferences } from '../src/state/initial';
import { calculateCosts, totalCosts } from '../src/agent/ranking';
import { preparePdfPlan } from '../src/booking/pdfData';
import { createTripPdf } from '../src/booking/tripPdf';
import type { RankedTrip } from '../src/types';

const preferences=() => { const p=initialPreferences(); p.startDate='2027-06-14'; p.nights=6; p.guests=2; p.slots.origin.value='Москва'; return p; };
const result = (id:string, p=preferences()): RankedTrip => {
  const trip=trips.find(t=>t.id===id)!; const costs=calculateCosts(trip,p);
  return {trip,costs,total:totalCosts(costs),score:1,reasons:[],compromises:[]};
};
const assets=async()=>({regular:new Uint8Array(await readFile('public/fonts/montserrat-regular.ttf')),semibold:new Uint8Array(await readFile('public/fonts/montserrat-semibold.ttf')),prata:new Uint8Array(await readFile('public/fonts/prata-regular.ttf'))});

describe('PDF itinerary',()=>{
  it('uses confirmed snapshot totals, dates and calculated check-in time',()=>{
    const p=preferences(), r=result('novisad',p), model=preparePdfPlan(r,p);
    expect(model.total).toBe(r.total); expect(model.guests).toBe(2);
    expect(model.start).toBe('2027-06-14'); expect(model.end).toBe('2027-06-20');
    expect(model.outbound.join(' ')).toContain('15:25');
    expect(model.outbound.join(' ')).toContain('Без пересадок');
  });
  it('never fabricates an unknown visa, transit, origin timezone, or optional details',()=>{
    const p=preferences(); p.passport='RU'; p.slots.origin.value='Неизвестный город';
    const r=result('lisbon',p); r.trip={...r.trip,stop:'',visaForRU:undefined as never,airport:'',hotel:{...r.trip.hotel,meals:''}};
    const model=preparePdfPlan(r,p); const text=JSON.stringify(model);
    expect(text).toContain('Визовые условия для паспорта РФ требуют уточнения');
    expect(text).toContain('Пересадки: требуют уточнения');
    expect(text).toContain('аэропорт уточняется'); expect(text).not.toContain('Europe/Moscow');
    expect(text).not.toContain('undefined'); expect(text).not.toContain('null');
  });
  it('handles an absent hotel and transfer without inventing details or crashing',()=>{
    const p=preferences(), r=result('lisbon',p);
    r.trip={...r.trip,hotel:undefined as never,transferMinutes:undefined as never};
    const text=JSON.stringify(preparePdfPlan(r,p));
    expect(text).toContain('Требует уточнения'); expect(text).toContain('время уточняется');
    expect(text).not.toContain('undefined'); expect(text).not.toContain('NaN');
  });
  it('generates one A4 page for direct and connecting routes',async()=>{
    const p=preferences(), fontAssets=await assets();
    for (const id of ['novisad','lisbon']) {
      const bytes=await createTripPdf(result(id,p),p,fontAssets,new Date('2026-10-27T12:00:00Z'));
      expect(new TextDecoder().decode(bytes.slice(0,5))).toBe('%PDF-');
      const pdf=await PDFDocument.load(bytes); expect(pdf.getPageCount()).toBe(1);
      expect(pdf.getPage(0).getWidth()).toBeCloseTo(595.28,1); expect(pdf.getPage(0).getHeight()).toBeCloseTo(841.89,1);
    }
  },20000);
  it('rejects excessive content instead of silently cropping important information',async()=>{
    const p=preferences(), r=result('lisbon',p); r.compromises=Array.from({length:50},()=> 'Обязательное важное условие должно оставаться видимым в документе.');
    await expect(createTripPdf(r,p,await assets())).rejects.toThrow(/слишком подробный/);
  },20000);
});
