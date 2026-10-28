import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await mkdir('test-results/rebuild',{recursive:true});
await page.goto(process.env.BASE_URL||'http://localhost:8080');await page.evaluate(()=>document.fonts.ready);
await page.screenshot({animations:'disabled',path:'test-results/rebuild/welcome.png'});
await page.getByLabel('Опишите поездку').fill('12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, 6 ночей, 1 взрослый, до 130 тысяч');
await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();await page.locator('.journey-card').first().waitFor();
await page.locator('img').evaluateAll(images=>Promise.all(images.map(i=>{i.loading='eager';return i.decode().catch(()=>{});}))); 
await page.screenshot({animations:'disabled',path:'test-results/rebuild/workspace-desktop.png'});
await page.locator('.compact-journey button').nth(1).click();await page.locator('.route-timeline').waitFor();await page.screenshot({animations:'disabled',path:'test-results/rebuild/route-details.png'});await page.keyboard.press('Escape');
const layouts=[];
for(const width of [390,768,1024,1280,1440,1920]) {
 await page.setViewportSize({width,height:900});
 const dims=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight}));
 assert(dims.document<=width);layouts.push(dims);
}
await page.setViewportSize({width:390,height:844});await page.screenshot({animations:'disabled',path:'test-results/rebuild/workspace-mobile.png'});
await page.locator('.mobile-tabs').getByRole('button',{name:'Чат',exact:false}).click();await page.getByLabel('Ваше сообщение').waitFor();await page.screenshot({animations:'disabled',path:'test-results/rebuild/chat-mobile.png'});
await page.locator('.mobile-tabs').getByRole('button',{name:'Поездки',exact:false}).click();await page.locator('.choose-trip').first().click();await page.getByRole('dialog').waitFor();await page.screenshot({animations:'disabled',path:'test-results/rebuild/booking-mobile.png'});
await page.locator('img').evaluateAll(images=>Promise.all(images.map(i=>i.decode().catch(()=>{}))));
const imageFailures=await page.locator('img').evaluateAll(images=>images.filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src));
assert.deepEqual(errors,[]);assert.deepEqual(imageFailures,[]);
await writeFile('test-results/rebuild/visual-checks.json',JSON.stringify({errors,imageFailures,layouts},null,2));await browser.close();console.log('Visual screenshots captured: desktop, mobile, complete route and booking. No image or JavaScript failures.');
