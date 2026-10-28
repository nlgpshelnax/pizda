import type { Costs, Preferences, RankedTrip, Trip } from '../types';
import { trips } from '../data/trips';
import { money } from '../shared/format';

export { money } from '../shared/format';
export const totalCosts = (c: Costs) => c.transport + c.hotel + c.transfer + c.extras;
export function calculateCosts(trip: Trip, p: Preferences): Costs {
  const originFactor = !p.slots.origin.value || p.slots.origin.value === 'Москва' ? 1 : 1.12;
  return {
    transport: Math.round(trip.costs.transport * p.guests * originFactor / 100) * 100,
    hotel: Math.round(trip.costs.hotel * p.nights / 6 * Math.ceil(p.guests / 2) / 100) * 100,
    transfer: trip.costs.transfer + (p.privateTransfer ? 3500 : 0),
    extras: Math.round((trip.costs.extras * p.guests + (p.pet ? 6000 : 0)) * p.nights / 6 / 100) * 100,
  };
}
export function destinationMatches(trip: Trip, p: Preferences) {
  const value = p.slots.destination.value;
  return !value || value === 'Европа' || [...trip.destinationKeys, trip.city, trip.country, trip.region].includes(value);
}
export function rankTrips(p: Preferences, catalog: Trip[] = trips): RankedTrip[] {
  // A supplied slot is independent of demo coverage. Never invent transport for an unsupported origin.
  if (p.slots.origin.catalogSupport === 'unsupported') return [];
  const additionalPurposes = p.unknownPurposes ?? [];
  if (additionalPurposes.some(wish => wish.strict)) return [];
  return catalog.flatMap(trip => {
    const costs = calculateCosts(trip, p); const total = totalCosts(costs);
    if (!destinationMatches(trip, p)) return [];
    if (additionalPurposes.length && !p.purposes.some(purpose => trip.purposes.includes(purpose)) &&
        !additionalPurposes.some(wish => wish.related?.some(purpose => trip.purposes.includes(purpose)))) return [];
    if (p.purposes.length && !p.purposes.some(purpose => trip.purposes.includes(purpose))) return [];
    if (p.budget && total > p.budget) return [];
    if (p.starsStrict && p.stars && trip.hotel.stars < p.stars) return [];
    if (p.pet && !trip.hotel.pets) return [];
    if (p.visaFree && p.visaStrict && (p.passport !== 'RU' || trip.visaForRU !== 'free')) return [];
    if (p.seaOnly && p.purposes.includes('beach') && (!p.month || !trip.warmSea.includes(p.month))) return [];
    let score = 40; const reasons: string[] = []; const compromises: string[] = [];
    for (const wish of additionalPurposes) {
      const related = wish.related?.some(purpose => trip.purposes.includes(purpose));
      if (related) score += 6;
      compromises.push(`«${wish.value}» не подтверждено в каталоге${related ? '; показан близкий тип отдыха' : '; выполнены только остальные пожелания'}`);
    }
    if (p.slots.destination.value) { score += 20; reasons.push(`Направление: ${trip.region}`); }
    if (p.month && trip.seasons.includes(p.month)) { score += 8; reasons.push('Подходит для выбранного сезона'); }
    if (p.month && !trip.seasons.includes(p.month)) { score -= 15; compromises.push('Несезон: часть активностей может быть недоступна'); }
    for (const purpose of p.purposes) {
      if (trip.purposes.includes(purpose)) score += 12;
      else { score -= 18; compromises.push(purpose === 'mountains' ? 'Нет горных активностей' : purpose === 'beach' ? 'Городской отдых вместо пляжного' : 'Не все занятия из запроса доступны'); }
    }
    if (p.purposes.includes('beach') && p.month && !trip.warmSea.includes(p.month)) {
      score -= 15;
      if (trip.heatedPool) { score += 12; compromises.push('Вместо тёплого моря: подогреваемый бассейн' + (p.poolAccepted ? ' (согласовано)' : ' (нужно ваше согласие)')); }
      else compromises.push('Море в этом месяце прохладное');
    }
    if (p.poolAccepted && !trip.heatedPool) return [];
    if (p.poolAccepted) reasons.push('Есть согласованный подогреваемый бассейн');
    if (p.budget) { reasons.push(`В пределах ${money(p.budget)}`); score += 8; }
    if (p.stars) {
      if (trip.hotel.stars >= p.stars) { score += 10; reasons.push(`Отель ${trip.hotel.stars}★`); }
      else { score -= 10; compromises.push(`${trip.hotel.stars}★ вместо желаемых ${p.stars}★`); }
    }
    if (p.pet) { score += 10; reasons.push('В отеле разрешён питомец'); }
    if (p.central) { if (trip.central) { score += 12; reasons.push('Отель в центре'); } else compromises.push('Отель расположен за пределами центра'); }
    if (p.visaFree) {
      if (p.passport === 'RU' && trip.visaForRU === 'free') { score += 12; reasons.push('Учебный безвизовый сценарий для паспорта РФ'); }
      else { score -= 15; compromises.push('Необходимо уточнить визовые условия'); }
    }
    if (trip.stop === 'Без пересадок') { score += 5; reasons.push('Предварительный маршрут без пересадок'); }
    if (!reasons.length) reasons.push('Сбалансированная стоимость и насыщенная программа');
    if (p.purposes.length) reasons.unshift('Занятия: ' + trip.activities.slice(0, 2).join(', ').toLowerCase());
    return [{ trip, score, reasons, compromises: [...new Set(compromises)], costs, total }];
  }).sort((a, b) => b.score - a.score || a.total - b.total || a.trip.id.localeCompare(b.trip.id)).slice(0, 5);
}
