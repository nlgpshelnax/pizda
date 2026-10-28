import type { Preferences, SlotKey } from '../types';

export const slotKeys: SlotKey[] = ['when', 'destination', 'origin', 'purpose'];
export function canSearch(p: Preferences): boolean {
  const known = slotKeys.filter(key => p.slots[key].status !== 'NO' && p.slots[key].value.trim());
  return known.length >= 3 || (known.length === 2 && known.includes('when') && known.includes('origin'));
}
export function clarification(p: Preferences): string {
  if (p.slots.origin.status === 'NO') return 'Из какого города начнём путешествие?';
  if (p.slots.when.status === 'NO') return 'Когда хотите поехать? Подойдёт месяц, сезон или точная дата.';
  if (p.slots.purpose.status === 'NO') return 'Чего хочется от поездки: прогулок, моря, гор или SPA?';
  return 'Какое направление вам интересно? Можно назвать город, страну или Европу целиком.';
}
