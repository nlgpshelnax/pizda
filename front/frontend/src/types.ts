import type { ReminderBooking, ReminderSettings } from './reminders/model';
export type SlotKey = 'when' | 'destination' | 'origin' | 'purpose';
export type SlotStatus = 'YES' | 'Vague' | 'NO';
export interface Slot {
  value: string; status: SlotStatus;
  rawValue?: string;
  resolution?: 'resolved' | 'unresolved';
  catalogSupport?: 'supported' | 'unsupported' | 'unknown';
}
export type Purpose = 'beach' | 'culture' | 'mountains' | 'spa' | 'walks';
export interface Preferences {
  agentState?: Record<string, unknown>;
  slots: Record<SlotKey, Slot>;
  month?: number;
  startDate?: string;
  nights: number;
  nightsEstimated: boolean;
  guests: number;
  guestsEstimated: boolean;
  budget?: number;
  stars?: number;
  starsStrict: boolean;
  visaFree: boolean;
  visaStrict: boolean;
  passport?: 'RU' | 'OTHER';
  pet: boolean;
  petStrict: boolean;
  seaOnly: boolean;
  poolAccepted: boolean;
  central: boolean;
  earlyCheckin: boolean;
  privateTransfer: boolean;
  purposes: Purpose[];
  unknownPurposes?: { value: string; strict: boolean; related?: Purpose[] }[];
  pendingInput?: string;
  awaitingSlot?: SlotKey;
}
export interface Message { id: string; role: 'user' | 'agent'; text: string }
export interface Costs { transport: number; hotel: number; transfer: number; extras: number }
export interface Hotel {
  name: string; stars: number; rating: string; description: string;
  amenities: string[]; meals: string; pets: boolean; checkin: string; checkinUntil: string; checkout: string;
}
export interface Trip {
  id: string; country: string; city: string; region: string;
  destinationKeys: string[]; airport: string; image: string;
  title: string; subtitle: string; hotel: Hotel;
  purposes: Purpose[]; seasons: number[]; warmSea: number[];
  heatedPool: boolean; central: boolean; visaForRU: 'required' | 'free';
  visaNote: string; costs: Costs; flightHours: string; transferMinutes: number;
  stop: string; arrival: string; outbound: string; returnDeparture: string;
  activities: string[]; risk: string;
}
export interface Alternative { label: string; message: string }
export interface Conflict { id: string; title: string; description: string; hard: boolean; alternatives: Alternative[] }
export interface RankedTrip { trip: Trip; score: number; reasons: string[]; compromises: string[]; costs: Costs; total: number }
export interface AgentRequest { text: string; preferences: Preferences; selectedId?: string; slotContext?: SlotKey }
export interface AgentResponse {
  preferences: Preferences; message: string; canSearch: boolean; conflicts: Conflict[];
  results: RankedTrip[]; changes: string[];
}
export interface AgentAdapter { respond(request: AgentRequest): Promise<AgentResponse> }
export interface Session {
  preferences: Preferences; messages: Message[]; results: RankedTrip[];
  conflicts: Conflict[]; canSearch: boolean; activeId?: string; selectedId?: string;
  booked: boolean; revision: number;
  selectedResult?: RankedTrip;
  booking?: ReminderBooking & { status: 'confirmed' | 'needs-confirmation' | 'cancelled' };
  reminderSettings?: ReminderSettings;
}
