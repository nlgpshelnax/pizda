import { describe, expect, it } from 'vitest';
import type { SlotKey } from '../src/types';
import { initialPreferences, initialSession } from '../src/state/initial';
import { canSearch } from '../src/agent/blocker';
import { parseMessage } from '../src/agent/parser';
import { processRequest } from '../src/agent/adapter';
import { applyResponse } from '../src/state/session';
import { calculateCosts, rankTrips, totalCosts } from '../src/agent/ranking';
import { checkConflicts, scheduleProblems } from '../src/agent/conflicts';
import { trips } from '../src/data/trips';
import { flightExample, localInstant } from '../src/agent/itinerary';

const parse = (text: string) => parseMessage(text, initialPreferences()).preferences;
describe('Blocker: все 16 комбинаций четырёх слотов', () => {
  const keys: SlotKey[] = ['when', 'destination', 'origin', 'purpose'];
  for (let mask = 0; mask < 16; mask++) {
    const included = keys.filter((_, i) => mask & (1 << i));
    it(`${included.join(' + ') || 'нет параметров'}`, () => {
      const p = initialPreferences();
      for (const key of included) p.slots[key] = { status: key === 'destination' ? 'Vague' : 'YES', value: 'полезное значение' };
      expect(canSearch(p)).toBe(included.length >= 3 || (included.length === 2 && included.includes('when') && included.includes('origin')));
    });
  }
  it('не считает пустое Vague полезным параметром', () => {
    const p = parse('В декабре'); p.slots.origin = { status: 'Vague', value: '' }; expect(canSearch(p)).toBe(false);
  });
});
describe('Распознавание и накопление контекста', () => {
  it.each(['из Питера', 'из СПб', 'из Санкт-Петербурга'])('%s → Санкт-Петербург', text => expect(parse(text).slots.origin.value).toBe('Санкт-Петербург'));
  it.each(['В декабре из Москвы', 'Летом из Москвы'])('разрешает предварительный подбор: %s', text => expect(canSearch(parse(text))).toBe(true));
  it('не ищет при when + destination', () => { const r = processRequest({ text: 'В декабре в Италию', preferences: initialPreferences() }); expect(r.canSearch).toBe(false); expect(r.message).toContain('Из какого города'); });
  it('ищет по трём слотам без даты', () => expect(canSearch(parse('Из Санкт-Петербурга в Испанию, хочу посмотреть архитектуру'))).toBe(true));
  it('не создаёт направление и цель из бессодержательных слов', () => { const p = parse('Куда-нибудь, хочу отдохнуть'); expect(p.slots.destination.status).toBe('NO'); expect(p.slots.purpose.status).toBe('NO'); });
  it('сохраняет месяц без конкретной даты', () => { const p = parse('В декабре из Москвы'); expect(p.month).toBe(12); expect(p.startDate).toBeUndefined(); expect(p.guestsEstimated).toBe(true); });
  it('понимает дату, диапазон и гостей', () => { const p = parse('С 12 по 18 декабря из Москвы, 2 взрослых'); expect(p.startDate).toBe('2026-12-12'); expect(p.nights).toBe(6); expect(p.guests).toBe(2); expect(p.guestsEstimated).toBe(false); });
  it('обновляет несколько условий, сохраняя остальные', () => { const before = parse('В декабре из Москвы в Сербию, хочу прогулки'); const p = parseMessage('Теперь с нами собака, бюджет до 90 тысяч, отель 4 звезды', before).preferences; expect(p.pet).toBe(true); expect(p.budget).toBe(90000); expect(p.stars).toBe(4); expect(p.slots).toEqual(before.slots); });
  it('«подешевле» снижает бюджет воспроизводимо', () => { const p = parseMessage('Хочу сэкономить', parse('Бюджет до 100 тысяч')).preferences; expect(p.budget).toBe(80000); });
  it('сдвигает точную дату на два дня', () => { const p = parseMessage('На два дня позже', parse('12 декабря')).preferences; expect(p.startDate).toBe('2026-12-14'); });
  it('не выдумывает точную дату из месяца при сдвиге', () => { const r = parseMessage('На два дня позже', parse('В декабре')); expect(r.preferences.startDate).toBeUndefined(); expect(r.unsupported).toBeTruthy(); });
  it('можно заменить 5★ на 4★', () => { const p = parseMessage('Сделай вместо пяти звёзд четыре', parse('Только 5 звезд')).preferences; expect(p.stars).toBe(4); expect(p.starsStrict).toBe(false); });
  it('не теряет данные на неизвестном сообщении', () => { const p = parse('В декабре из Москвы'); const r = processRequest({ text: 'абракадабра 123', preferences: p }); expect(r.preferences).toEqual(p); expect(r.message).toContain('ограниченным'); });
  it('различает пожелание и жёсткое требование', () => { expect(parse('Желательно 5 звезд').starsStrict).toBe(false); expect(parse('Только 5 звезд').starsStrict).toBe(true); });
  it('жёсткость относится к своему условию', () => { const p = parse('Желательно 4 звезды, только без визы'); expect(p.starsStrict).toBe(false); expect(p.visaStrict).toBe(true); });
});
describe('Конфликты и ограничения', () => {
  it('зимнее море предлагает бассейн и не называет его точным совпадением', () => {
    const p = parse('В декабре из Москвы в Европу, хочу купаться в море');
    expect(checkConflicts(p).some(c => c.id === 'winter-sea')).toBe(true);
    expect(rankTrips(p).some(r => r.compromises.some(c => c.includes('бассейн')))).toBe(true);
  });
  it('«только море» не подменяется бассейном', () => { const p = parse('В декабре из Москвы в Европу, только теплое море, бассейн не подходит'); expect(p.seaOnly).toBe(true); expect(rankTrips(p)).toHaveLength(0); expect(checkConflicts(p)[0].hard).toBe(true); });
  it('при смене месяца обязательное море сохраняется', () => { const p = parseMessage('В июле хочу купаться в море', parse('В декабре из Москвы, только море')).preferences; expect(p.seaOnly).toBe(true); expect(rankTrips(p).every(r => r.trip.warmSea.includes(7))).toBe(true); });
  it('согласие на бассейн разрешает компромисс', () => { const p = parseMessage('Согласен на подогреваемый бассейн вместо моря', parse('В декабре из Москвы в Европу, только море')).preferences; expect(p.poolAccepted).toBe(true); expect(checkConflicts(p).some(c => c.id === 'winter-sea')).toBe(false); expect(rankTrips(p).length).toBeGreaterThan(0); expect(rankTrips(p).every(r => r.trip.heatedPool)).toBe(true); });
  it('замена моря на SPA убирает сезонный конфликт', () => { const p = parseMessage('Вместо моря хочу SPA', parse('В декабре из Москвы, хочу купаться')).preferences; expect(p.purposes).toEqual(['spa']); expect(checkConflicts(p).some(c => c.id === 'winter-sea')).toBe(false); });
  it('«только 5★» и маленький бюджет дают пустой результат', () => { const p = parse('В декабре из Москвы в Европу, только 5 звезд, до 60 тысяч'); expect(rankTrips(p)).toHaveLength(0); expect(checkConflicts(p).some(c => c.id === 'stars-budget' && c.hard)).toBe(true); });
  it('мягкое пожелание 5★ допускает явно помеченный компромисс', () => { const p = parse('В декабре из Москвы в Европу, желательно 5 звезд, бюджет до 90 тысяч'); const results = rankTrips(p); expect(results.length).toBeGreaterThan(0); expect(results.every(r => r.total <= 90000 && r.compromises.some(c => c.includes('вместо')))).toBe(true); });
  it('питомец исключает отели, где животные запрещены', () => { const p = parse('В декабре из Москвы, с нами собака'); expect(rankTrips(p).every(r => r.trip.hotel.pets)).toBe(true); });
  it('безвизовый фильтр не угадывает гражданство', () => { const p = parse('В декабре из Москвы, только без визы'); expect(p.passport).toBeUndefined(); expect(rankTrips(p)).toHaveLength(0); expect(checkConflicts(p).some(c => c.id === 'passport')).toBe(true); });
  it('после уточнения паспорта фильтрует визовые варианты', () => { const p = parse('В декабре из Москвы, без визы, паспорт РФ'); const r = rankTrips(p); expect(r.length).toBeGreaterThan(0); expect(r.every(x => x.trip.visaForRU === 'free')).toBe(true); });
  it('не заполняет результаты неподходящими странами', () => { const r = rankTrips(parse('В декабре из Москвы в Италию, хочу музеи')); expect(r.length).toBe(2); expect(r.every(x => x.trip.country === 'Италия')).toBe(true); });
});
describe('Финансы и маршрут', () => {
  it('в каталоге 15 уникальных вымышленных предложений', () => { expect(trips.length).toBe(15); expect(new Set(trips.map(t => t.id)).size).toBe(15); });
  it('не более 5 вариантов, детерминированное ранжирование', () => { const p = parse('В декабре из Москвы'); expect(rankTrips(p)).toHaveLength(5); expect(rankTrips(p)).toEqual(rankTrips(p)); });
  it('итог равен сумме компонентов при разных гостях и длительности', () => {
    for (const t of trips) for (const guests of [1, 2, 3]) for (const nights of [3, 6, 9]) {
      const p = { ...initialPreferences(), guests, nights, pet: true, privateTransfer: true };
      const c = calculateCosts(t, p); expect(totalCosts(c)).toBe(c.transport + c.hotel + c.transfer + c.extras); expect(Object.values(c).every(n => n >= 0)).toBe(true);
    }
  });
  it('каталог учитывает регистрацию и резерв до обратного рейса', () => { for (const t of trips) expect(scheduleProblems(t), t.id).toEqual([]); });
  it('обнаруживает позднее заселение и недостаток времени перед вылетом', () => { const t = structuredClone(trips[0]); t.arrival = '23:40'; t.returnDeparture = '11:30'; expect(scheduleProblems(t)).toHaveLength(2); });
  it('учитывает летнее и зимнее местное время', () => { expect(localInstant('2026-12-12', '13:10', 'Europe/Rome').toISOString()).toBe('2026-12-12T12:10:00.000Z'); expect(localInstant('2027-07-12', '13:10', 'Europe/Rome').toISOString()).toBe('2027-07-12T11:10:00.000Z'); });
  it('длительность рейса и пересадки согласована с местными временами', () => {
    const p = parse('12 декабря из Екатеринбурга');
    for (const t of trips) {
      const f = flightExample(t, p, '2026-12-12', '2026-12-18');
      expect((f.arrivalInstant.getTime()-f.departureInstant.getTime())/60000).toBe(f.duration);
      expect((f.returnArrivalInstant.getTime()-f.returnInstant.getTime())/60000).toBe(f.duration);
      expect(f.connectionMinutes).toBe(t.stop === 'Без пересадок' ? 0 : 120);
    }
  });
});
describe('Переходы состояния', () => {
  it('пересборка сохраняет сообщения, но снимает неподходящий выбор', () => {
    const s = initialSession(); const first = processRequest({ text: 'В декабре из Москвы в Испанию, хочу архитектуру', preferences: s.preferences });
    const updated = applyResponse(s, first); updated.selectedId = 'barcelona'; updated.activeId = 'barcelona'; updated.booked = true; updated.messages = [{ id:'1', role:'user', text:'Исходный запрос' }];
    const response = processRequest({ text: 'Теперь только без визы, паспорт РФ', preferences: updated.preferences }); const next = applyResponse(updated, response);
    expect(next.messages).toEqual(updated.messages); expect(next.selectedId).toBeUndefined(); expect(next.booked).toBe(false); expect(next.preferences.slots.origin).toEqual(updated.preferences.slots.origin);
  });
  it('изменение даты требует повторного оформления', () => {
    const s = applyResponse(initialSession(), processRequest({ text:'12 декабря из Москвы в Сербию, 1 взрослый', preferences: initialPreferences() }));
    s.selectedId = s.results[0].trip.id; s.booked = true;
    const next = applyResponse(s, processRequest({text:'На два дня позже', preferences:s.preferences})); expect(next.booked).toBe(false); expect(next.selectedId).toBe(s.selectedId);
  });
});
