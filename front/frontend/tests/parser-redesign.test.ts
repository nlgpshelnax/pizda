import { describe, expect, it } from 'vitest';
import { initialPreferences } from '../src/state/initial';
import { parseMessage } from '../src/agent/parser';
import { processRequest } from '../src/agent/adapter';
import { canSearch } from '../src/agent/blocker';
import { rankTrips } from '../src/agent/ranking';

describe('Значение, смысл и поддержка каталога разделены', () => {
  it('сохраняет явно указанное неизвестное направление как заполненный слот', () => {
    const p = parseMessage('В декабре из Москвы в Антананариву', initialPreferences()).preferences;
    expect(p.slots.destination).toMatchObject({ value:'Антананариву', status:'YES', resolution:'unresolved', catalogSupport:'unsupported', rawValue:'Антананариву' });
    expect(canSearch(p)).toBe(true);
    expect(rankTrips(p)).toEqual([]);
  });
  it('объясняет отсутствие покрытия, не просит повторно указать уже сохранённый город', () => {
    const r = processRequest({ text:'В декабре из Москвы в Антананариву', preferences:initialPreferences() });
    expect(r.canSearch).toBe(true);
    expect(r.message).toContain('Запомнил направление: Антананариву');
    expect(r.message).toContain('В демо-каталоге');
    expect(r.conflicts.some(c => c.id === 'destination-coverage')).toBe(true);
  });
  it('не подменяет неизвестный город отправления Москвой', () => {
    const r = processRequest({ text:'В декабре из Антананариву', preferences:initialPreferences() });
    expect(r.preferences.slots.origin.value).toBe('Антананариву');
    expect(r.preferences.slots.origin.status).toBe('YES');
    expect(r.canSearch).toBe(true);
    expect(r.results).toHaveLength(0);
    expect(r.message).toContain('не буду');
  });
  it('сохраняет известный по смыслу, но неподдерживаемый город отправления', () => {
    const p = parseMessage('Из Рима в Барселону в июне', initialPreferences()).preferences;
    expect(p.slots.origin).toMatchObject({value:'Рим',resolution:'resolved',catalogSupport:'unsupported'});
    expect(p.slots.destination.value).toBe('Барселона');
  });
  it('после уточняющего вопроса понимает роль короткого ответа', () => {
    const first = processRequest({ text:'В декабре в Италию', preferences:initialPreferences() });
    expect(first.preferences.awaitingSlot).toBe('origin');
    const second = processRequest({ text:'Антананариву', preferences:first.preferences });
    expect(second.preferences.slots.origin.value).toBe('Антананариву');
    expect(second.preferences.slots.destination.value).toBe('Италия');
    expect(second.canSearch).toBe(true);
  });
  it('использует явный контекст редактора параметра', () => {
    const r = processRequest({text:'Антананариву',preferences:initialPreferences(),slotContext:'destination'});
    expect(r.preferences.slots.destination.value).toBe('Антананариву');
    expect(r.preferences.pendingInput).toBeUndefined();
  });
  it('сохраняет неоднозначное название и задаёт вопрос о его роли', () => {
    const first = processRequest({text:'Антананариву',preferences:initialPreferences()});
    expect(first.preferences.pendingInput).toBe('Антананариву');
    expect(first.preferences.slots.destination.status).toBe('NO');
    expect(first.message).toContain('назначения или отправления');
    const second = processRequest({text:'Это направление',preferences:first.preferences});
    expect(second.preferences.slots.destination.value).toBe('Антананариву');
    expect(second.preferences.pendingInput).toBeUndefined();
  });
  it('разрешает явную смену неподдерживаемого направления, сохраняя остальные слоты', () => {
    const first = processRequest({text:'В декабре из Москвы в Антананариву',preferences:initialPreferences()});
    const second = processRequest({text:'В Италию',preferences:first.preferences});
    expect(second.preferences.slots.destination.catalogSupport).toBe('supported');
    expect(second.preferences.slots.origin.value).toBe('Москва');
    expect(second.preferences.month).toBe(12);
    expect(second.results.length).toBeGreaterThan(0);
  });
  it('не определяет SPA из слова «Испания»', () => {
    const p = parseMessage('Из Питера в Испанию, хочу архитектуру',initialPreferences()).preferences;
    expect(p.purposes).toEqual(['culture']);
  });
  it('не считает относительный перенос даты новым направлением', () => {
    const initial = parseMessage('12 декабря из Москвы в Сербию',initialPreferences()).preferences;
    const p = parseMessage('На два дня позже',initial).preferences;
    expect(p.slots.destination).toEqual(initial.slots.destination);
    expect(p.startDate).toBe('2026-12-14');
  });
});

describe('Неподдерживаемая цель остаётся пожеланием пользователя', () => {
  it('сохраняет дайвинг отдельно от пляжной категории', () => {
    const r = processRequest({text:'В июле из Москвы, хочу заняться дайвингом',preferences:initialPreferences()});
    expect(r.preferences.slots.purpose.status).toBe('YES');
    expect(r.preferences.slots.purpose.value).toContain('дайвингом');
    expect(r.preferences.slots.purpose.catalogSupport).toBe('unsupported');
    expect(r.preferences.unknownPurposes?.[0].related).toEqual(['beach']);
    expect(r.preferences.purposes).toEqual([]);
    expect(r.canSearch).toBe(true);
    expect(r.results.length).toBeGreaterThan(0);
    expect(r.results.every(r => r.trip.purposes.includes('beach') && r.compromises.some(c => c.includes('не подтверждено')))).toBe(true);
  });
  it('не выдаёт пляжный отдых за выполнение обязательного дайвинга', () => {
    const r = processRequest({text:'В июле из Москвы, хочу заняться только дайвингом',preferences:initialPreferences()});
    expect(r.preferences.unknownPurposes?.[0].strict).toBe(true);
    expect(r.results).toHaveLength(0);
    expect(r.conflicts.some(c => c.id === 'purpose-coverage' && c.hard)).toBe(true);
  });
  it('не заполняет результаты произвольными поездками для неизвестного занятия', () => {
    const r = processRequest({text:'В декабре из Москвы, хочу заняться наблюдением за кометами',preferences:initialPreferences()});
    expect(r.preferences.slots.purpose.value).toContain('кометами');
    expect(r.preferences.slots.purpose.resolution).toBe('unresolved');
    expect(r.results).toHaveLength(0);
    expect(r.message).toContain('Сохранил пожелание');
  });
  it('сохраняет неизвестную цель без глагола «заняться», даже в полном запросе', () => {
    const r = processRequest({text:'В декабре из Москвы, хочу фототур',preferences:initialPreferences()});
    expect(r.preferences.slots.purpose.value.toLowerCase()).toContain('фототур');
    expect(r.preferences.slots.purpose.status).toBe('YES');
    expect(r.canSearch).toBe(true);
    expect(r.results).toHaveLength(0);
  });
  it('не считает визовое изменение неизвестной целью', () => {
    const initial = parseMessage('В июле из Москвы, хочу прогулки',initialPreferences()).preferences;
    const p = parseMessage('Не хочу оформлять визу',initial).preferences;
    expect(p.visaFree).toBe(true);
    expect(p.slots.purpose).toEqual(initial.slots.purpose);
    expect(p.unknownPurposes).toBeUndefined();
  });
  it('при принятии другой цели снимает только прежнее пожелание', () => {
    const first = processRequest({text:'В июле из Москвы, хочу заняться только дайвингом',preferences:initialPreferences()});
    const second = processRequest({text:'Согласен на пляжный отдых вместо прежней цели',preferences:first.preferences});
    expect(second.preferences.unknownPurposes).toBeUndefined();
    expect(second.preferences.purposes).toEqual(['beach']);
    expect(second.preferences.slots.origin.value).toBe('Москва');
    expect(second.results.length).toBeGreaterThan(0);
  });
  it('сохраняет неизвестную цель из контекстного редактора', () => {
    const r = processRequest({text:'Ловить северное сияние',preferences:initialPreferences(),slotContext:'purpose'});
    expect(r.preferences.slots.purpose).toMatchObject({status:'YES',catalogSupport:'unsupported',rawValue:'Ловить северное сияние'});
  });
});
