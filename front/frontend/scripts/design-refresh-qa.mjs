import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

const base = process.env.BASE_URL || 'http://localhost:8080';
const directory = 'test-results/design-refresh';
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
const results = [];
await mkdir(directory, { recursive: true });

for (const [width, height] of [[1440, 900], [1280, 800], [1024, 768], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const capture = async name => {
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${directory}/${name}-${width}x${height}.png`, animations: 'disabled' });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert.equal(overflow, false, `${name}: horizontal overflow at ${width}`);
  };
  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await capture('start');
  await page.getByLabel('Опишите поездку').fill('12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, 6 ночей, 1 взрослый, до 130 тысяч');
  await page.getByRole('button', { name: 'Отправить сообщение', exact: true }).click();
  await page.locator('.journey-card').first().waitFor();
  assert.equal(await page.locator('.journey-card').count(), 2);
  assert.equal(await page.locator('.compact-journey').count(), 3);
  if (width >= 768) {
    const [chat, resultsPane] = await Promise.all([page.locator('.chat-panel').boundingBox(), page.locator('.workspace').boundingBox()]);
    assert(Math.abs(chat.width / (chat.width + resultsPane.width) - 0.4) < 0.002, 'desktop chat occupies 40%');
  }
  await capture('results');
  await page.locator('.compact-journey button').nth(1).click();
  await page.locator('.route-timeline').waitFor();
  await capture('route');
  await page.keyboard.press('Escape');
  await page.locator('.choose-trip').first().click();
  await page.getByRole('dialog').waitFor();
  await capture('booking');
  const imageFailures = await page.locator('img').evaluateAll(images => images.filter(image => !image.complete || !image.naturalWidth).map(image => image.src));
  assert.deepEqual(imageFailures, []);
  assert.deepEqual(errors, []);
  results.push({ width, height, screens: ['start', 'results', 'route', 'booking'], images: 'loaded', pageErrors: errors });
  await page.close();
}
await writeFile(`${directory}/report.json`, JSON.stringify(results, null, 2));
await browser.close();
console.log(`Captured ${results.length * 4} screens and checked layout, results, images and runtime errors.`);
