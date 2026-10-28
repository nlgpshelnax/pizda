import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const reports=[];
await mkdir('test-results/pdf',{recursive:true});
try {
  for (const [name,query] of [
    ['direct','12 июня 2027 из Москвы в Сербию, хочу прогулки, 1 взрослый'],
    ['connection','12 июня 2027 из Москвы в Португалию, хочу прогулки, 1 взрослый'],
  ]) {
    const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true});
    await page.goto('http://localhost:8080/');
    await page.getByLabel('Опишите поездку').fill(query);
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    await page.locator('.journey-card').first().waitFor();
    await page.locator('.route-preview-heading button').first().click();
    await expect(page.getByRole('dialog').getByText('Скачать план', {exact:false})).toHaveCount(0);
    await page.keyboard.press('Escape');
    await page.locator('.choose-trip').first().click();
    await expect(page.getByRole('button',{name:'Скачать план PDF'})).toHaveCount(0);
    await page.getByLabel('Дата начала',{exact:true}).fill('2027-06-14');
    await page.getByLabel('Взрослые',{exact:true}).fill('2');
    const total=await page.locator('.booking-live-total strong').innerText();
    await page.getByRole('checkbox').check();
    await page.getByRole('button',{name:'Оформить демо-поездку',exact:true}).click();
    await expect(page.locator('.booking-confirmed')).toBeVisible();
    const downloadPromise=page.waitForEvent('download',{timeout:25000});
    await page.getByRole('button',{name:'Скачать план PDF'}).click();
    const download=await downloadPromise;
    const filename=`test-results/pdf/${name}.pdf`;
    await download.saveAs(filename);
    const bytes=await readFile(filename);
    assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
    reports.push({name,total:total.replace(/\s/g,''),date:'14.06.2027',guests:'2 взр.'});
    console.log(`${name}: ${download.suggestedFilename()}, ${bytes.length} bytes, UI total ${total}`);
    await page.getByRole('button',{name:'Изменить даты и гостей'}).click();
    await expect(page.getByRole('button',{name:'Скачать план PDF'})).toHaveCount(0);
    await page.close();
  }
  await writeFile('test-results/pdf/ui-data.json',JSON.stringify(reports,null,2));
} finally { await browser.close(); }
