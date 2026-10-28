import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || (process.platform==='win32'?'msedge':undefined),headless:true});
const base=process.env.BASE_URL || 'http://localhost:8080';
await mkdir('test-results/compositions',{recursive:true});
const report=[];
for(const layout of ['a','b']) {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}/composition-preview.html?layout=${layout}`);
  await page.evaluate(()=>document.fonts.ready);
  await page.locator('img').evaluateAll(images=>Promise.all(images.map(i=>i.decode().catch(()=>{}))));
  await page.screenshot({path:`test-results/compositions/option-${layout}-desktop.png`,animations:'disabled'});
  for(const [width,height] of [[1920,900],[1440,900],[1280,768],[1024,768],[768,900],[390,844],[375,812]]) {
    await page.setViewportSize({width,height});
    const dimensions=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight}));
    assert(dimensions.scrollWidth<=width,`${layout}: horizontal overflow at ${width}`);
    if(width>=1280) {
      const action=page.locator(layout==='a'?'.cp-offer.is-expanded .cp-primary':'.cp-plan-footer .cp-primary');
      const box=await action.boundingBox();assert(box && box.y+box.height<=height,`${layout}: CTA outside viewport at ${width}`);
    }
    if(width===390) await page.screenshot({path:`test-results/compositions/option-${layout}-mobile.png`,animations:'disabled'});
    report.push({layout,...dimensions});
  }
  await page.setViewportSize({width:1440,height:900});
  if(layout==='a') {
    const old=await page.locator('.cp-offer.is-expanded h2').innerText();
    await page.locator('.cp-offer:not(.is-expanded) .cp-open').first().click();
    assert.notEqual(await page.locator('.cp-offer.is-expanded h2').innerText(),old);
    await page.locator('.cp-offer.is-expanded .cp-disclosure').click();
    await expect(page.locator('.cp-cost-list')).toBeVisible();
  } else {
    await page.locator('.cp-choice').filter({hasText:'Барселона'}).click();
    await expect(page.locator('.cp-route-heading h1')).toHaveText('Барселона');
    await expect(page.locator('.cp-itinerary')).toContainText('Patio del Sol');
  }
  await page.getByLabel('Изменить пожелания').fill('Хочу подешевле');
  await page.getByRole('button',{name:'Отправить сообщение'}).click();
  await expect(page.locator('.cp-message-agent')).toHaveCount(2);
  const imageFailures=await page.locator('img').evaluateAll(images=>images.filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src));
  assert.deepEqual(errors,[]);assert.deepEqual(imageFailures,[]);
  await page.close();
}
await writeFile('test-results/compositions/review.json',JSON.stringify(report,null,2));
await browser.close();
console.log('Both compositions rendered, screenshots captured, layout and interactions checked.');
