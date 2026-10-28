import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

// Frozen Date keeps future/past reminder assertions reproducible; browser timers remain real.
const fixedNow = new Date('2026-10-26T09:00:00.000Z');
const storageKey = 'odin-travel-session-v2';
const base = process.env.BASE_URL || 'http://localhost:8080';
const channel = process.env.BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined);
const browser = await chromium.launch({ channel, headless: true });
const report = [];
const layouts = [];
await mkdir('test-results', { recursive: true });

async function openPage(context, width = 1440) {
  const page = await context.newPage();
  await page.setViewportSize({ width, height: 768 });
  await page.clock.setFixedTime(fixedNow);
  await page.goto(base);
  await page.evaluate(() => document.fonts.ready);
  return page;
}
async function scenario(name, run) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 768 }, acceptDownloads: true });
  const page = await openPage(context);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await run(page, context);
    assert.deepEqual(errors, [], 'No JavaScript errors');
    report.push({ name, status: 'passed' });
    console.log('PASS', name);
  } catch (error) {
    report.push({ name, status: 'failed', error: error.message });
    console.log('FAIL', name, error.message);
    await page.screenshot({ animations:'disabled', path: `test-results/redesign-failure-${report.length}.png`, fullPage: true });
  } finally { await context.close(); }
}
async function saved(page) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key) || 'null'), storageKey);
}
async function send(page, text) {
  const mobile = await page.locator('.mobile-tabs').isVisible();
  if (mobile) await page.getByRole('button', { name: 'Чат', exact: false }).click();
  const count = await page.locator('.message-agent').count();
  await page.locator('textarea:visible').fill(text);
  await page.getByRole('button', { name: 'Отправить сообщение', exact: true }).click();
  await expect.poll(() => page.locator('.message-agent').count()).toBe(count + 1);
  if (mobile) await page.locator('.mobile-tabs').getByRole('button', { name: 'Поездки', exact: false }).click();
}
async function editSlot(page, index, value) {
  await page.locator('.parameter').nth(index).click();
  await page.getByLabel('Новое условие', { exact: true }).fill(value);
  const count = await page.locator('.message-agent').count();
  await page.getByRole('button', { name: 'Обновить поездку', exact: true }).click();
  await expect.poll(() => page.locator('.message-agent').count()).toBe(count + 1);
}
async function review(page, query = 'В декабре из Москвы в Сербию, хочу прогулки') {
  await send(page, query);
  await expect(page.locator('.trip-card').first()).toBeVisible();
  await page.locator('.choose-trip').first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
}
async function confirm(page, date = '2027-06-12') {
  await page.getByLabel('Дата начала', { exact: true }).fill(date);
  await page.getByRole('checkbox').check();
  await expect(page.getByRole('button', { name: 'Оформить демо-поездку', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Оформить демо-поездку', exact: true }).click();
  await expect(page.locator('.booking-confirmed')).toBeVisible();
}
const reminderSwitch = page => page.getByRole('switch', { name: 'Включить напоминания о поездке', exact: true });
const reminderChoice = (page, label) => page.locator('.reminder-option').filter({ hasText: label }).getByRole('checkbox');
async function allReminders(page) {
  await reminderSwitch(page).check();
  for (const label of ['За 7 дней', 'За 1 день', 'За 3 часа']) await reminderChoice(page, label).check();
  await page.getByRole('button', { name: 'Сохранить напоминания', exact: true }).click();
  await expect(page.locator('.reminder-summary')).toContainText('Ближайшее');
  await expect.poll(async () => (await saved(page)).reminderSettings.schedule.length).toBe(3);
}
async function downloadCalendar(page) {
  const promise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать событие .ics', exact: true }).click();
  const download = await promise;
  assert(download.suggestedFilename().endsWith('.ics'));
  const path = await download.path();
  assert(path, 'Calendar download has a readable file');
  return readFile(path, 'utf8');
}
const amount = value => Number(value.replace(/[^0-9]/g, ''));
const isoIcs = value => new Date(value).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');

await scenario('Simplified navigation and explicit unknown destination stay separate from catalog coverage', async page => {
  await expect(page.locator('.avatar')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Как это работает', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Новая поездка', exact: true })).toHaveCount(0);
  await send(page, 'В декабре из Москвы в Антананариву');
  await expect(page.locator('.parameter').nth(1)).toContainText('Антананариву');
  await expect(page.locator('.parameter').nth(1)).toContainText('Сохранено');
  const session = await saved(page);
  assert.equal(session.preferences.slots.destination.value, 'Антананариву');
  assert.equal(session.preferences.slots.destination.status, 'YES');
  assert.equal(session.preferences.slots.destination.catalogSupport, 'unsupported');
  assert.equal(session.canSearch, true, 'Three useful slots pass unchanged Blocker');
  await expect(page.locator('.trip-card')).toHaveCount(0);
  await expect(page.locator('.empty-state')).toContainText('Антананариву');
  assert((await page.locator('.empty-state').boundingBox()).height < 300, 'Empty state is compact');
  await expect(page.getByRole('button', { name: 'Новая поездка', exact: true })).toHaveCount(1);
});

await scenario('Bare city is retained, role clarification and parameter editing preserve it', async page => {
  await send(page, 'Антананариву');
  assert.equal((await saved(page)).preferences.pendingInput, 'Антананариву');
  await expect(page.locator('.message-agent').last()).toContainText('город назначения или отправления');
  await send(page, 'Это город назначения');
  assert.equal((await saved(page)).preferences.slots.destination.value, 'Антананариву');
  await editSlot(page, 1, 'Барселона');
  assert.equal((await saved(page)).preferences.slots.destination.value, 'Барселона');
  await editSlot(page, 1, 'Антананариву');
  const slot = (await saved(page)).preferences.slots.destination;
  assert.equal(slot.value, 'Антананариву');
  assert.equal(slot.status, 'YES');
  assert.equal(slot.catalogSupport, 'unsupported');
});

await scenario('Unknown origin remains origin and never receives invented demo transport', async page => {
  await send(page, 'В декабре из Антананариву, хочу прогулки');
  const session = await saved(page);
  assert.equal(session.preferences.slots.origin.value, 'Антананариву');
  assert.equal(session.preferences.slots.origin.status, 'YES');
  assert.equal(session.preferences.slots.origin.catalogSupport, 'unsupported');
  assert.equal(session.canSearch, true);
  assert.equal(session.results.length, 0);
  await expect(page.locator('.empty-state')).toContainText('Маршрута');
  await expect(page.locator('.parameter').nth(2)).toContainText('Антананариву');
});

await scenario('Unsupported diving is saved as a soft wish, strict diving never silently matches', async page => {
  await send(page, 'В июне из Москвы в Европу, хочу заняться дайвингом');
  const soft = await saved(page);
  assert.match(soft.preferences.slots.purpose.value, /дайвинг/i);
  assert.equal(soft.preferences.slots.purpose.status, 'YES');
  assert.equal(soft.preferences.slots.purpose.catalogSupport, 'unsupported');
  assert(soft.results.length > 0, 'Only genuine nearby beach alternatives are offered');
  assert(soft.results.every(result => result.compromises.some(value => /дайвинг/i.test(value))), 'Every soft alternative identifies the unmet diving wish');
  await expect(page.locator('.trip-card .reasoning').first()).toContainText('дайвинг');
  await send(page, 'Хочу только заняться дайвингом');
  const strict = await saved(page);
  assert.equal(strict.preferences.unknownPurposes[0].strict, true);
  assert.equal(strict.results.length, 0);
  await expect(page.locator('.empty-state')).toBeVisible();
  await expect(page.locator('.parameter').nth(3)).toContainText('дайвинг');
});

await scenario('Booking edits recalculate and persist automatically, local invalid input stays local, one final confirmation', async page => {
  await review(page);
  const messageCount = await page.locator('.message-agent').count();
  await expect(page.getByRole('button', { name: 'Уточнить детали и пересчитать', exact: true })).toHaveCount(0);
  await page.getByLabel('Дата начала', { exact: true }).fill('2027-06-12');
  await expect.poll(async () => (await saved(page)).preferences.startDate).toBe('2027-06-12');
  const initialPrice = amount(await page.locator('.booking-live-total strong').innerText());
  await page.getByLabel('Взрослые', { exact: true }).fill('2');
  await expect.poll(async () => amount(await page.locator('.booking-live-total strong').innerText())).toBeGreaterThan(initialPrice);
  assert.equal((await saved(page)).preferences.guests, 2);
  await page.getByLabel('Откуда', { exact: true }).fill('Казань');
  const afterOrigin = await saved(page);
  assert.equal(afterOrigin.preferences.slots.origin.value, 'Казань');
  assert.equal(amount(await page.locator('.booking-live-total strong').innerText()), afterOrigin.selectedResult.total);
  await expect(page.getByRole('dialog').locator('.route-preview')).toContainText('Казань');
  await page.getByLabel('Взрослые', { exact: true }).fill('0');
  await expect(page.locator('#booking-guests-error')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Оформить демо-поездку', exact: true })).toBeDisabled();
  assert.equal((await saved(page)).preferences.guests, 2, 'Invalid draft does not corrupt persisted valid count');
  await page.getByLabel('Взрослые', { exact: true }).fill('2');
  await page.getByLabel('Дата начала', { exact: true }).fill('');
  await expect(page.locator('#booking-date-error')).toBeVisible();
  await expect(page.locator('.booking-live-total strong')).toHaveCount(0);
  await page.getByLabel('Дата начала', { exact: true }).fill('2027-06-12');
  await page.getByLabel('Откуда', { exact: true }).fill('Антананариву');
  await expect(page.locator('#booking-origin-error')).toContainText('Город сохранён');
  assert.equal((await saved(page)).preferences.slots.origin.value, 'Антананариву');
  await page.getByLabel('Откуда', { exact: true }).fill('Москва');
  await expect(page.getByRole('checkbox')).toBeVisible();
  await page.getByRole('checkbox').check();
  await expect(page.getByRole('button', { name: 'Оформить демо-поездку', exact: true })).toBeEnabled();
  await expect(page.locator('.message-agent')).toHaveCount(messageCount);
  await page.getByRole('button', { name: 'Оформить демо-поездку', exact: true }).evaluate(button => { button.click(); button.click(); });
  await expect(page.locator('.booking-confirmed')).toContainText('Демо-поездка оформлена');
  const booked = await saved(page);
  assert.equal(booked.booked, true);
  assert.equal(booked.booking.preferences.startDate, '2027-06-12');
  assert.equal(booked.booking.preferences.guests, 2);
  assert.equal(booked.booking.result.total, booked.selectedResult.total);
  assert.equal(booked.messages.filter(m => /Демо-поездка оформлена\./.test(m.text)).length, 1, 'Repeated click creates one confirmation');
});

await scenario('Reminder switch, multiple offsets and downloaded calendar contain the actual saved alarms', async page => {
  await review(page); await confirm(page); await allReminders(page);
  const before = await saved(page);
  const schedule = before.reminderSettings.schedule;
  const departure = Date.parse(schedule.find(item => item.offset === '3h').at) + 3 * 3600000;
  for (const [offset, milliseconds] of [['7d', 7 * 86400000], ['1d', 86400000], ['3h', 3 * 3600000]]) {
    const item = schedule.find(value => value.offset === offset);
    assert.equal(Date.parse(item.at), departure - milliseconds);
    assert(Date.parse(item.at) > fixedNow.getTime());
  }
  const calendar = await downloadCalendar(page);
  const unfolded = calendar.replace(/\r\n[ \t]/g, '');
  assert(calendar.includes('\r\n'), 'Calendar uses CRLF');
  assert.equal((calendar.match(/BEGIN:VALARM/g) || []).length, 3);
  assert(unfolded.includes(`DTSTART:${isoIcs(new Date(departure))}`));
  assert(/DTEND:\d{8}T\d{6}Z/.test(unfolded));
  assert(unfolded.includes(before.booking.result.trip.city));
  for (const trigger of ['-P7D', '-P1D', '-PT3H']) assert(unfolded.includes(`TRIGGER;RELATED=START:${trigger}`));
  await expect(page.locator('.reminder-help')).toContainText('при его использовании');
  await expect(page.locator('.reminder-help')).toContainText('календарь');
  assert(!/уведомление доставлено|письмо отправлено|sms отправлено|push отправлен/i.test(await page.getByRole('dialog').innerText()));
  await page.screenshot({ animations:'disabled', path: 'test-results/after-redesign-reminders.png' });
  await reminderSwitch(page).uncheck();
  assert.equal((await saved(page)).reminderSettings.enabled, false);
  assert.deepEqual((await saved(page)).reminderSettings.schedule, []);
  assert.equal(((await downloadCalendar(page)).match(/BEGIN:VALARM/g) || []).length, 0);
  await allReminders(page);
});

await scenario('Closing and reopening browser context restores confirmed trip, preferences and nearest reminder', async (page, context) => {
  await review(page); await confirm(page); await allReminders(page);
  const before = await saved(page);
  const state = await context.storageState();
  const reopened = await browser.newContext({ storageState: state, viewport: { width: 1280, height: 768 }, acceptDownloads: true });
  try {
    const next = await openPage(reopened, 1280);
    await expect(next.locator('.booked-banner')).toContainText('Ближайшее напоминание');
    const after = await saved(next);
    assert.equal(after.booking.id, before.booking.id);
    assert.equal(after.booking.preferences.startDate, before.booking.preferences.startDate);
    assert.deepEqual(after.reminderSettings, before.reminderSettings);
    await next.getByRole('button', { name: 'Моя поездка', exact: true }).click();
    await expect(reminderSwitch(next)).toBeChecked();
    await expect(next.locator('.reminder-summary')).toContainText('Ближайшее');
    await expect(next.locator('.reminder-saved-times')).toContainText('За 7 дней');
  } finally { await reopened.close(); }
});

await scenario('Opening app after a saved reminder time shows an in-app notice without delivery claims', async (page,context)=>{
  await review(page);await confirm(page);await allReminders(page);
  const before=await saved(page);
  const oneDay=before.reminderSettings.schedule.find(item=>item.offset==='1d');
  const state=await context.storageState();
  const reopened=await browser.newContext({storageState:state,viewport:{width:1280,height:768}});
  try {
    const next=await reopened.newPage();
    await next.clock.setFixedTime(new Date(Date.parse(oneDay.at)+60000));
    await next.goto(base);
    await expect(next.locator('.booking-status')).toContainText('Наступило напоминание');
    await next.getByRole('button',{name:'Моя поездка',exact:true}).click();
    await expect(next.locator('.reminder-due')).toContainText('Время проверить детали поездки');
    assert(!/уведомление доставлено|письмо отправлено|sms отправлено|push отправлен/i.test(await next.getByRole('dialog').innerText()));
  } finally {await reopened.close();}
});

await scenario('Date edits deactivate old alarms and re-confirmed trip recalculates chosen times', async page => {
  await review(page); await confirm(page); await allReminders(page);
  const before = await saved(page);
  await page.getByRole('button', { name: 'Изменить даты и гостей', exact: true }).click();
  await page.getByLabel('Дата начала', { exact: true }).fill('2027-06-14');
  const changed = await saved(page);
  assert.equal(changed.booked, false);
  assert.equal(changed.booking.status, 'needs-confirmation');
  assert.equal(changed.reminderSettings.enabled, false);
  assert.equal(changed.reminderSettings.schedule.length, 0);
  assert.deepEqual(changed.reminderSettings.offsets, before.reminderSettings.offsets);
  await expect(page.getByRole('dialog')).toContainText('Прежние напоминания отключены');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Оформить демо-поездку', exact: true }).click();
  await expect(page.locator('.booking-confirmed')).toBeVisible();
  await allReminders(page);
  const after = await saved(page);
  assert.equal(after.booking.preferences.startDate, '2027-06-14');
  for (const item of before.reminderSettings.schedule) {
    const updated = after.reminderSettings.schedule.find(value => value.offset === item.offset);
    assert.equal(Date.parse(updated.at) - Date.parse(item.at), 2 * 86400000);
  }
});

await scenario('Explicit cancellation disables alarms and remains cancelled after reload', async page => {
  await review(page); await confirm(page); await allReminders(page);
  await page.getByRole('button', { name: 'Отменить демо-бронирование', exact: true }).click();
  await page.getByRole('button', { name: 'Да, отменить', exact: true }).click();
  const session = await saved(page);
  assert.equal(session.booked, false);
  assert.equal(session.booking.status, 'cancelled');
  assert.equal(session.reminderSettings.enabled, false);
  assert.equal(session.reminderSettings.schedule.length, 0);
  await expect(page.getByRole('dialog', {name:'Бронирование отменено'})).toBeVisible();
  await page.reload();
  await expect(page.locator('.booked-banner')).toHaveCount(0);
  assert.equal((await saved(page)).booking.status, 'cancelled');
  await page.getByRole('button', { name: 'Моя поездка', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Напоминания на сайте выключены');
});

await scenario('Past reminder times are disabled and never exported', async page => {
  await review(page, '2026-10-27 из Москвы в Сербию, хочу прогулки, 1 взрослый');
  await confirm(page, '2026-10-27');
  await reminderSwitch(page).check();
  await expect(reminderChoice(page, 'За 7 дней')).toBeDisabled();
  await expect(reminderChoice(page, 'За 1 день')).toBeDisabled();
  await expect(reminderChoice(page, 'За 3 часа')).toBeEnabled();
  await reminderChoice(page, 'За 3 часа').check();
  await page.getByRole('button', { name: 'Сохранить напоминания', exact: true }).click();
  const session = await saved(page);
  assert.equal(session.reminderSettings.schedule.length, 1);
  assert.equal(session.reminderSettings.schedule[0].offset, '3h');
  assert(Date.parse(session.reminderSettings.schedule[0].at) > fixedNow.getTime());
  const calendar = await downloadCalendar(page);
  assert.equal((calendar.match(/BEGIN:VALARM/g) || []).length, 1);
  assert(calendar.includes('TRIGGER;RELATED=START:-PT3H'));
  assert(!calendar.includes('TRIGGER;RELATED=START:-P7D'));
  assert(!calendar.includes('TRIGGER;RELATED=START:-P1D'));
});

await scenario('Responsive 390–1920: 40/60 split, two main trips, route access and reachable composer', async page => {
  await send(page,'12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, 1 взрослый, до 130 тысяч');
  for (const width of [390,768,1024,1280,1440,1920]) {
    await page.setViewportSize({width,height:900});
    const mobile=width<768;
    if(mobile)await page.locator('.mobile-tabs').getByRole('button',{name:'Поездки',exact:false}).click();
    const dimensions=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight}));
    assert(dimensions.scrollWidth<=width,'No horizontal overflow');
    assert(dimensions.scrollHeight<=901,'Page remains within viewport');
    await expect(page.locator('.journey-card')).toHaveCount(2);
    await expect(page.locator('.compact-journey')).toHaveCount(3);
    await expect(page.locator('.journey-card .route-preview').first()).toContainText('Прибытие');
    if(!mobile) {
      const chat=await page.locator('.chat-panel').boundingBox();
      const work=await page.locator('.workspace').boundingBox();
      assert(Math.abs(chat.width/width-.4)<.002,'Chat occupies 40 percent');
      assert(Math.abs(work.width/width-.6)<.002,'Trips occupy 60 percent');
      assert(chat.x+chat.width<=work.x+1,'Panels do not overlap');
      const cards=await page.locator('.journey-card').evaluateAll(cards=>cards.map(card=>({x:card.getBoundingClientRect().x,y:card.getBoundingClientRect().y,height:card.getBoundingClientRect().height})));
      if(width>=1280)assert(Math.abs(cards[0].y-cards[1].y)<=1&&cards[1].x>cards[0].x,'Two main trips sit side by side');
      else assert(cards[1].y>cards[0].y,'Medium screens stack the main trips');
      const composer=await page.locator('.chat-panel .composer').boundingBox();
      assert(composer&&composer.y+composer.height<=900,'Composer remains available');
      if(width===1440) {
        const last=await page.locator('.compact-journey .compact-bottom').last().boundingBox();
        assert(last&&last.y+last.height<=900,'All five trips can be read in first 1440x900 view');
      }
    } else {
      await page.getByRole('button',{name:'Чат',exact:false}).click();
      await expect(page.locator('.workspace')).not.toBeVisible();
      const composer=await page.locator('.chat-panel .composer').boundingBox();
      assert(composer&&composer.y+composer.height<=900,'Mobile input remains in viewport');
      await page.locator('.mobile-tabs').getByRole('button',{name:'Поездки',exact:false}).click();
    }
    await page.locator('img').evaluateAll(images=>Promise.all(images.map(i=>{i.loading='eager';return i.decode().catch(()=>{});}))); 
    assert.deepEqual(await page.locator('img').evaluateAll(images=>images.filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src)),[]);
    await page.screenshot({animations:'disabled',path:'test-results/rebuild/final-'+width+'.png'});
    layouts.push(dimensions);
  }
});

await writeFile('test-results/redesign-e2e-report.json', JSON.stringify({ fixedNow: fixedNow.toISOString(), base, scenarios: report, layouts }, null, 2));
await browser.close();
const failures = report.filter(item => item.status !== 'passed');
console.log(`\n${report.length - failures.length}/${report.length} redesign browser scenarios passed`);
if (failures.length) process.exitCode = 1;
