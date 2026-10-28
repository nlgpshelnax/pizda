// Real integration check. No request interception and no substitute model responses.
import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
const ui = process.env.BASE_URL ?? 'http://localhost:8080';
const api = process.env.AGENT_API_URL ?? 'http://localhost:8000';
const ollama = process.env.OLLAMA_BASE_URL ?? 'http://localhost:11434/v1';
const model = process.env.OLLAMA_MODEL ?? 'qwen2.5:7b-instruct';
const models = await fetch(`${ollama}/models`).then(r => { assert(r.ok); return r.json(); });
assert(models.data.some(m => m.id === model), `Ollama model missing: ${model}`);
const health = await fetch(`${api}/api/health`).then(r => { assert(r.ok); return r.json(); });
assert.equal(health.status, 'ok');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(ui);
  for (const text of ['Хочу к морю в ноябре', 'Из Москвы']) {
    const responsePromise = page.waitForResponse(r => r.url() === `${api}/api/v1/chat` && r.request().method() === 'POST', { timeout: 360000 });
    await page.locator('textarea:visible').fill(text);
    await page.getByRole('button', { name: 'Отправить сообщение', exact: true }).click();
    const response = await responsePromise;
    assert.equal(response.status(), 200, `Agent HTTP ${response.status()}`);
    const body = await response.json();
    assert(body.message?.trim());
    assert(body.preferences.agentState);
    await expect(page.locator('.message-agent').last()).toHaveText(body.message, { timeout: 10000 });
    console.log('PASS: UI → Agent HTTP API → Qwen → UI');
  }
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
