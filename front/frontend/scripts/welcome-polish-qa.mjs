import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';

const directory='test-results/welcome-polish';
await mkdir(directory,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
const report=[];
try {
  for(const [width,height] of [[1440,900],[390,844]]) {
    const context=await browser.newContext({viewport:{width,height}});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.BASE_URL||'http://localhost:8080/');
    await page.evaluate(()=>document.fonts.ready);
    const photo=page.locator('.welcome-photo img');
    await photo.evaluate(image=>image.decode());
    await expect(page.getByLabel('Опишите поездку')).toBeVisible();
    await expect(page.locator('.welcome-examples button')).toHaveCount(3);
    const form=await page.locator('.welcome .composer').boundingBox();
    const image=await photo.boundingBox();
    assert(form&&image);
    assert(form.y>=0&&form.y+form.height<=height,'Input and send control fit the first screen');
    if(width===1440)assert(image.x>form.x+form.width,'Photo is to the right on desktop');
    else assert(image.y>form.y+form.height,'Photo follows the input on a phone');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow');
    const imageState=await photo.evaluate(image=>({width:image.naturalWidth,height:image.naturalHeight,src:new URL(image.currentSrc).pathname,fit:getComputedStyle(image).objectFit,position:getComputedStyle(image).objectPosition}));
    assert.equal(imageState.src,'/images/welcome/coast.webp');assert(imageState.width>=1200);assert.equal(imageState.fit,'cover');
    await page.screenshot({path:`${directory}/welcome-${width}.png`,animations:'disabled'});
    // A real first request must enter the existing working application.
    await page.getByLabel('Опишите поездку').fill('12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, 1 взрослый, до 130 тысяч');
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    await expect(page.locator('.journey-card')).toHaveCount(2);
    await expect(page.locator('.compact-journey')).toHaveCount(3);
    await expect(page.locator('.message-agent')).toHaveCount(1);
    if(width===1440) {
      const chat=await page.locator('.chat-panel').boundingBox();
      const trips=await page.locator('.workspace').boundingBox();
      assert(Math.abs(chat.width/width-.4)<.002&&Math.abs(trips.width/width-.6)<.002,'Existing 40/60 composition is preserved');
    }
    await page.screenshot({path:`${directory}/working-${width}.png`,animations:'disabled'});
    assert.deepEqual(errors,[]);
    report.push({width,height,image:imageState,inputInFirstScreen:true,firstRequest:'passed',javascriptErrors:errors});
    await context.close();
  }
  const page=await browser.newPage();
  await page.goto(process.env.BASE_URL||'http://localhost:8080/');
  for(const width of [320,375,768,1024,1280,1920]) {
    await page.setViewportSize({width,height:900});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No overflow at ${width}`);
  }
  await page.close();
  const examples=[
    {label:'Прогулки в Португалии',query:'Хочу прогулки в Португалии',destination:'Португалия',purposes:['walks']},
    {label:'Архитектура в Италии',query:'Хочу архитектуру в Италии',destination:'Италия',purposes:['culture']},
    {label:'Горы и SPA',query:'Хочу горы и SPA',destination:'',purposes:['mountains','spa']},
  ];
  for(const [index,example] of examples.entries()) {
    const context=await browser.newContext({viewport:{width:1440,height:900}});
    const examplePage=await context.newPage();
    await examplePage.goto(process.env.BASE_URL||'http://localhost:8080/');
    await examplePage.getByRole('button',{name:example.label,exact:true}).click();
    await expect(examplePage.locator('.message-user p')).toHaveText(example.query);
    await expect(examplePage.locator('.message-agent').last()).toBeVisible();
    const preferences=await examplePage.evaluate(()=>JSON.parse(localStorage.getItem('odin-travel-session-v2')).preferences);
    assert.equal(preferences.slots.origin.status,'NO');
    assert.equal(preferences.slots.origin.value,'');
    assert.equal(preferences.slots.when.status,'NO');
    assert.equal(preferences.slots.when.value,'');
    assert.equal(preferences.month,undefined);
    assert.equal(preferences.budget,undefined);
    assert.equal(preferences.slots.destination.value,example.destination);
    assert.deepEqual(preferences.purposes,example.purposes);
    await expect(examplePage.locator('.message-agent').last()).toContainText('Из какого города');
    await expect(examplePage.locator('.trip-card')).toHaveCount(0);
    await examplePage.screenshot({path:`${directory}/example-${index+1}.png`,animations:'disabled'});
    await context.close();
  }
  await writeFile(`${directory}/qa-report.json`,JSON.stringify({examples:'passed without invented origin, date or budget',screens:report},null,2));
  console.log('Welcome screenshots, first requests, and all examples passed without inventing a city, date, or budget.');
} finally {await browser.close();}
