import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge', headless:true});
await mkdir('test-results/calendar',{recursive:true});
try {
  for (const [width,height] of [[320,844],[390,844],[1440,900]]) {
    const page=await browser.newPage({viewport:{width,height}});
    const errors=[];page.on('pageerror', error=>errors.push(error.message));
    await page.clock.setFixedTime(new Date('2026-10-27T12:00:00Z'));
    await page.goto('http://localhost:8080/');
    await page.getByLabel('Опишите поездку').fill('12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, 1 взрослый, до 130 тысяч');
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    await page.locator('.choose-trip').first().click();
    const booking=page.getByRole('dialog',{name:'Детали поездки'});
    await expect(booking).toBeVisible();
    const input=booking.getByLabel('Дата начала');
    await expect(input).toHaveValue('2027-06-12');
    await input.click();
    await expect(booking).toBeVisible();
    await booking.getByRole('button',{name:'Открыть календарь'}).click();
    const calendar=page.getByRole('dialog',{name:'Выберите дату начала'});
    await expect(calendar).toBeVisible();
    await expect(calendar.getByRole('button',{name:'12 июня 2027 г.'})).toBeFocused();
    await page.screenshot({path:`test-results/calendar/open-${width}.png`,animations:'disabled'});
    await page.keyboard.press('ArrowRight');
    await expect(calendar.getByRole('button',{name:'13 июня 2027 г.'})).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(calendar).not.toBeVisible();
    await expect(input).toHaveValue('2027-06-13');
    await expect(booking.getByRole('button',{name:'Открыть календарь'})).toBeFocused();
    await booking.getByRole('button',{name:'Открыть календарь'}).click();
    await page.keyboard.press('Escape');
    await expect(calendar).not.toBeVisible();
    await expect(booking).toBeVisible();
    await expect(booking.getByRole('button',{name:'Открыть календарь'})).toBeFocused();
    await input.fill('2027-06-14');
    await expect(input).toHaveValue('2027-06-14');
    await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('odin-travel-session-v2')).preferences.startDate)).toBe('2027-06-14');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    await page.close();
  }
  console.log('Calendar passed: 320, 390 and 1440 px; keyboard selection, Escape, focus restore, direct date entry and persistence.');
} finally {await browser.close();}
