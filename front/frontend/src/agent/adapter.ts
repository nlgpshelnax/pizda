import type { AgentAdapter, AgentRequest, AgentResponse, SlotKey } from '../types';
import { parseMessage } from './parser';
import { canSearch, clarification } from './blocker';
import { checkConflicts } from './conflicts';
import { rankTrips } from './ranking';

const labels: Record<string, string> = { when: 'время поездки', destination: 'направление', origin: 'город отправления', purpose: 'цель', budget: 'бюджет', pet: 'питомец', stars: 'категория отеля', visa: 'визовые пожелания', passport: 'гражданство', nights: 'длительность', guests: 'число гостей', central: 'расположение отеля', earlyCheckin: 'запрос раннего заезда', transfer: 'трансфер' };
export function processRequest(request: AgentRequest): AgentResponse {
  const previousResults = rankTrips(request.preferences);
  const selectedTotal = previousResults.find(r => r.trip.id === request.selectedId)?.total;
  const parsed = parseMessage(request.text, request.preferences, selectedTotal, request.slotContext);
  const preferences = parsed.preferences;
  const allowed = canSearch(preferences);
  const conflicts = checkConflicts(preferences);
  const results = allowed ? rankTrips(preferences) : [];
  let message: string;
  if (parsed.unsupported) message = parsed.unsupported;
  else if (preferences.pendingInput) message = `Сохранил «${preferences.pendingInput}». Это город назначения или отправления?`;
  else if (!parsed.recognized) message = 'Демо работает с ограниченным набором формулировок. Уточните город, месяц, занятие или условие. Текущие параметры сохранены.';
  else if (preferences.slots.destination.catalogSupport === 'unsupported') message = `Запомнил направление: ${preferences.slots.destination.value}. В демо-каталоге поездок туда пока нет. Пожелание сохранено; можно выбрать другое направление.${!allowed ? ' ' + clarification(preferences) : ''}`;
  else if (preferences.slots.origin.catalogSupport === 'unsupported') message = `Запомнил город отправления: ${preferences.slots.origin.value}. В демо нет маршрутов из этого города; подменять его другим не буду.${!allowed ? ' ' + clarification(preferences) : ''}`;
  else if (preferences.unknownPurposes?.length) {
    const wish = preferences.unknownPurposes.map(item => `«${item.value}»`).join(', ');
    message = `Сохранил пожелание ${wish}. ${results.length ? 'Показал близкие варианты с пометкой о невыполненном пожелании.' : 'В каталоге это занятие не подтверждено.'}${!allowed ? ' ' + clarification(preferences) : ''}`;
  }
  else if (!allowed) message = `Запомнил ${parsed.changes.map(c => labels[c] ?? c).join(', ')}. ${clarification(preferences)}`;
  else if (conflicts.some(c => c.hard)) message = 'Обязательные условия пока не сходятся. Параметры сохранены; способы решения показаны в плане.';
  else if (!results.length) message = 'Под эти условия поездок в демо-каталоге нет. Параметры сохранены; проверьте бюджет, направление или категорию отеля.';
  else {
    const hasHistory = Object.values(request.preferences.slots).some(s => s.status !== 'NO');
    message = `${hasHistory ? 'Пересобрал' : 'Собрал'} ${results.length} ${results.length === 1 ? 'вариант' : results.length < 5 ? 'варианта' : 'вариантов'}.${hasHistory ? ` Обновил: ${parsed.changes.map(c => labels[c] ?? c).join(', ')}.` : ''}${conflicts.length ? ' Компромиссы отмечены в плане.' : ''}${!preferences.startDate ? ' Даты пока примерные.' : ''}`;
  }
  if (!allowed && !preferences.pendingInput && parsed.recognized) {
    const next = (['origin', 'when', 'purpose', 'destination'] as SlotKey[]).find(key => preferences.slots[key].status === 'NO');
    if (next) preferences.awaitingSlot = next;
  } else if (allowed) delete preferences.awaitingSlot;
  return { preferences, message, canSearch: allowed, conflicts, results, changes: parsed.changes };
}
export class MockAgentAdapter implements AgentAdapter {
  async respond(request: AgentRequest): Promise<AgentResponse> {
    await new Promise(resolve => setTimeout(resolve, 650));
    return processRequest(request);
  }
}

/** Production chat transport: failures are surfaced, never replaced by local answers. */
export class HttpAgentAdapter implements AgentAdapter {
  async respond(request: AgentRequest): Promise<AgentResponse> {
    const base = ((import.meta as ImportMeta & { env: Record<string, string | undefined> }).env.VITE_AGENT_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
    const response = await fetch(`${base}/api/v1/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request), signal: AbortSignal.timeout(360000),
    });
    if (!response.ok) throw new Error(`Agent HTTP ${response.status}`);
    return await response.json() as AgentResponse;
  }
}
