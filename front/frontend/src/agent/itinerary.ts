import type { Preferences, Trip } from '../types';

export function destinationZone(t: Trip): string {
  const zones: Record<string, string> = { 'Италия':'Europe/Rome', 'Франция':'Europe/Paris', 'Сербия':'Europe/Belgrade', 'Черногория':'Europe/Podgorica', 'Венгрия':'Europe/Budapest', 'Австрия':'Europe/Vienna', 'Греция':'Europe/Athens' };
  if (t.country === 'Португалия') return t.id === 'madeira' ? 'Atlantic/Madeira' : 'Europe/Lisbon';
  if (t.country === 'Испания') return t.id === 'tenerife' ? 'Atlantic/Canary' : 'Europe/Madrid';
  return zones[t.country] ?? 'UTC';
}
export function originZone(p: Preferences): string {
  return p.slots.origin.value === 'Екатеринбург' ? 'Asia/Yekaterinburg' : p.slots.origin.value === 'Новосибирск' ? 'Asia/Novosibirsk' : 'Europe/Moscow';
}
function localParts(instant: Date, zone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23' }).formatToParts(instant);
  const field = (key: string) => parts.find(p => p.type === key)?.value ?? '';
  return { date:`${field('year')}-${field('month')}-${field('day')}`, time:`${field('hour')}:${field('minute')}` };
}
export function localInstant(date: string, time: string, zone: string): Date {
  const expected = Date.parse(`${date}T${time}:00Z`);
  let candidate = new Date(expected);
  for (let i=0; i<2; i++) {
    const parts = localParts(candidate, zone);
    candidate = new Date(candidate.getTime() + expected - Date.parse(`${parts.date}T${parts.time}:00Z`));
  }
  return candidate;
}
export function flightExample(t: Trip, p: Preferences, start: string, end: string) {
  const hours = Number(t.flightHours.match(/(\d+)\s*ч/)?.[1] ?? 0);
  const mins = Number(t.flightHours.match(/(\d+)\s*мин/)?.[1] ?? 0);
  const duration = hours * 60 + mins;
  const arrivalInstant = localInstant(start, t.arrival, destinationZone(t));
  const departureInstant = new Date(arrivalInstant.getTime() - duration * 60000);
  const returnInstant = localInstant(end, t.returnDeparture, destinationZone(t));
  const returnArrivalInstant = new Date(returnInstant.getTime() + duration * 60000);
  const connectionMinutes = t.stop === 'Без пересадок' ? 0 : 120;
  const firstLeg = Math.min(200, duration - connectionMinutes - 60);
  const connectionArrival = new Date(departureInstant.getTime() + firstLeg * 60000);
  const connectionDeparture = new Date(connectionArrival.getTime() + connectionMinutes * 60000);
  return {
    departure: localParts(departureInstant, originZone(p)),
    arrival: localParts(arrivalInstant, destinationZone(t)),
    returnArrival: localParts(returnArrivalInstant, originZone(p)),
    connectionArrival: localParts(connectionArrival, 'Europe/Istanbul'),
    connectionDeparture: localParts(connectionDeparture, 'Europe/Istanbul'),
    connectionMinutes, duration, departureInstant, arrivalInstant, returnInstant, returnArrivalInstant,
  };
}
