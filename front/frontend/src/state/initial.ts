import type { Preferences, Session } from '../types';
export function initialPreferences(): Preferences {
  return {
    slots: { when: { value: '', status: 'NO' }, destination: { value: '', status: 'NO' }, origin: { value: '', status: 'NO' }, purpose: { value: '', status: 'NO' } },
    nights: 6, nightsEstimated: true, guests: 1, guestsEstimated: true,
    starsStrict: false, visaFree: false, visaStrict: false, pet: false, petStrict: true,
    seaOnly: false, poolAccepted: false, central: false, earlyCheckin: false, privateTransfer: false, purposes: [],
  };
}
export function initialSession(): Session {
  return { preferences: initialPreferences(), messages: [], results: [], conflicts: [], canSearch: false, booked: false, revision: 0 };
}
