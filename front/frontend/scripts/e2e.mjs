import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
const base=process.env.BASE_URL||'http://localhost:8080';
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||(process.platform==='win32'?'msedge':undefined),headless:true});
await mkdir('test-results/rebuild',{recursive:true});
const report=[];
const storage=page=>page.evaluate(()=>JSON.parse(localStorage.getItem('odin-travel-session-v2')));
async function scenario(name,run) {
 const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try {await page.clock.setFixedTime(new Date('2026-10-26T09:00:00Z'));await page.goto(base);await page.evaluate(()=>document.fonts.ready);await run(page);assert.deepEqual(errors,[]);report.push({name,status:'passed'});console.log('PASS',name);}
 catch(e){report.push({name,status:'failed',error:e.message});console.log('FAIL',name,e.message);await page.screenshot({path:`test-results/rebuild/failure-${report.length}.png`});}
 finally {await context.close();}
}
async function send(page,text) {
 const count=await page.locator('.message-agent').count();
 if(await page.locator('.mobile-tabs').isVisible())await page.getByRole('button',{name:'Чат',exact:false}).click();
 await page.locator('textarea:visible').fill(text);await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect.poll(()=>page.locator('.message-agent').count()).toBe(count+1);
 if(await page.locator('.mobile-tabs').isVisible())await page.locator('.mobile-tabs').getByRole('button',{name:'Поездки',exact:false}).click();
}
async function details(page,index=0) {await page.locator('.journey-card .route-preview-heading button').nth(index).click();await expect(page.locator('.route-timeline')).toBeVisible();}
async function close(page) {await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);}
const number=text=>Number(text.replace(/[^0-9]/g,''));
await scenario('Welcome, help, photo credits, keyboard shortcuts and focus',async page=>{
 await expect(page.locator('.welcome h1')).toHaveText('Куда хотите отправиться?');
 await page.getByRole('button',{name:'Как это работает',exact:true}).click();
 await page.getByRole('button',{name:'Фотографии и авторы'}).click();await expect(page.getByRole('dialog')).toContainText('ZlatanJovanovic');
 await close(page);
 const input=page.getByLabel('Опишите поездку');await input.fill('В декабре');await input.press('Shift+Enter');await input.pressSequentially('из Москвы');assert((await input.inputValue()).includes('\n'));await input.press('Enter');
 await expect(page.locator('.journey-card')).toHaveCount(2);
 await details(page);await page.keyboard.press('Tab');
 assert(await page.evaluate(()=>document.querySelector('dialog')?.contains(document.activeElement)),'Focus stays within dialog');
 await close(page);
});
await scenario('Blocker clarification, exact two-slot rule, unknown input and reset',async page=>{
 await send(page,'Хочу в Париж');await expect(page.locator('.waiting-state')).toBeVisible();
 await send(page,'В декабре');assert.equal((await storage(page)).canSearch,false);
 await send(page,'Из Москвы');await expect(page.locator('.journey-card')).toHaveCount(1);
 await send(page,'абракадабра');await expect(page.locator('.message-agent').last()).toContainText('ограниченным');
 await page.getByRole('button',{name:'Новая поездка',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Новая поездка',exact:false}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 await send(page,'В декабре из Москвы');assert.equal((await storage(page)).canSearch,true);await expect(page.locator('.trip-card, .compact-trip')).toHaveCount(5);
});
await scenario('Full trips: two main cards, three alternatives, route, costs and no export before booking',async page=>{
 await send(page,'12 июня 2027 из Москвы в Европу, хочу прогулки и архитектуру, до 130 тысяч');
 await expect(page.locator('.journey-card')).toHaveCount(2);await expect(page.locator('.compact-journey')).toHaveCount(3);
 for(const label of ['Перелёт','Прибытие','Трансфер','Заселение','Обратно'])await expect(page.locator('.route-preview').first()).toContainText(label);
 await details(page);await expect(page.locator('.route-timeline')).toContainText('60 мин');await expect(page.locator('.route-timeline')).toContainText('Выезд из отеля');await expect(page.locator('.route-timeline')).toContainText('Дома');
 await page.getByRole('dialog').locator('summary').filter({hasText:'Расходы и визовые условия'}).click();
 const amounts=await page.locator('.cost-row strong').allTextContents();assert.equal(amounts.reduce((s,v)=>s+number(v),0),number(await page.locator('.cost-total strong').innerText()));
 await expect(page.getByRole('dialog').getByRole('button',{name:/Скачать план/})).toHaveCount(0);
 assert.equal((await storage(page)).booked,false);await close(page);
 await page.locator('.compact-journey button').first().click();await expect(page.locator('.route-timeline')).toBeVisible();await expect(page.getByRole('dialog')).toContainText('Thermal House');await close(page);
});
await scenario('Favourites, comparison, sorting and fewer than five genuine matches',async page=>{
 await send(page,'В июне из Москвы в Италию, хочу архитектуру');await expect(page.locator('.journey-card')).toHaveCount(2);await expect(page.locator('.compact-journey')).toHaveCount(0);
 await page.locator('.journey-card .save-button').first().click();await page.getByRole('button',{name:'Показать сохранённые варианты'}).click();await expect(page.locator('.journey-card')).toHaveCount(1);
 await page.getByRole('button',{name:'Показать сохранённые варианты'}).click();await page.getByRole('button',{name:'Сравнить поездки'}).click();await expect(page.locator('.comparison-list>section')).toHaveCount(2);await close(page);
 await page.getByLabel('Сортировать поездки').selectOption('price');const totals=(await page.locator('.trip-price strong').allTextContents()).map(number);assert(totals[0]<=totals[1]);
});
await scenario('Winter sea explains compromise and requires explicit pool acceptance',async page=>{
 await send(page,'В декабре из Москвы в Европу хочу купаться в теплом море');await expect(page.locator('.conflict').first()).toContainText('прохладнее');
 await expect(page.locator('.journey-facts').first()).toContainText('Компромисс');await page.getByRole('button',{name:'Согласен на бассейн',exact:true}).click();
 await expect.poll(async()=>(await storage(page)).preferences.poolAccepted).toBe(true);
 await expect(page.locator('.conflict')).toHaveCount(0);assert((await storage(page)).preferences.poolAccepted);assert((await storage(page)).results.every(r=>r.trip.heatedPool));
});
await scenario('Strict sea is retained until user chooses the July alternative',async page=>{
 await send(page,'В декабре из Москвы в Европу, только теплое море, бассейн не подходит');await expect(page.locator('.journey-card')).toHaveCount(0);await expect(page.locator('.conflict-hard').first()).toBeVisible();
 await page.getByRole('button',{name:'Перенести на июль'}).click();await expect(page.locator('.journey-card').first()).toBeVisible();assert.equal((await storage(page)).preferences.month,7);assert.equal((await storage(page)).preferences.seaOnly,true);
});
await scenario('Impossible strict five-star budget offers an explicit four-star alternative',async page=>{
 await send(page,'В декабре из Москвы в Европу, только 5 звезд, бюджет до 90 тысяч');await expect(page.locator('.empty-state')).toBeVisible();
 await page.getByRole('button',{name:'Рассмотреть 4★'}).click();await expect(page.locator('.journey-card').first()).toBeVisible();assert((await storage(page)).results.every(r=>r.total<=90000));
});
await scenario('Selection, changed wishes, pet and visa conditions preserve context',async page=>{
 await send(page,'В декабре из Москвы, хочу прогулки');await page.locator('.compact-journey').filter({hasText:'Котор'}).getByRole('button').click();await page.getByRole('dialog').getByRole('button',{name:'Выбрать поездку',exact:true}).click();await expect(page.getByLabel('Дата начала',{exact:true})).toBeVisible();await close(page);
 await send(page,'Теперь с нами собака, хочу подешевле');await expect(page.locator('.parameters')).toContainText('С питомцем');assert.equal((await storage(page)).preferences.slots.origin.value,'Москва');
 await send(page,'Хочу без визы');await expect(page.locator('.conflict').first()).toContainText('нужен паспорт');await page.getByRole('button',{name:'У меня паспорт РФ'}).click();await expect(page.locator('.journey-card').first()).toContainText('Виза не нужна');assert.equal((await storage(page)).preferences.passport,'RU');
});
await scenario('Single booking action, automatic date/guest/origin updates and aftercare',async page=>{
 await send(page,'В декабре из Москвы в Сербию, хочу прогулки');await page.locator('.choose-trip').first().click();await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByLabel('Дата начала',{exact:true}).fill('2027-06-12');const total=number(await page.locator('.booking-live-total strong').innerText());
 await page.getByLabel('Взрослые',{exact:true}).fill('2');await expect.poll(async()=>number(await page.locator('.booking-live-total strong').innerText())).toBeGreaterThan(total);
 await page.getByLabel('Откуда',{exact:true}).fill('Казань');await expect(page.getByRole('dialog').locator('.route-preview')).toContainText('Казань');
 await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Оформить демо-поездку',exact:true}).click();await expect(page.locator('.booking-confirmed')).toBeVisible();
 const pdfDownload=page.waitForEvent('download');await page.getByRole('button',{name:'Скачать план PDF'}).click();const pdf=await pdfDownload;assert(pdf.suggestedFilename().endsWith('.pdf'));assert.equal((await readFile(await pdf.path())).subarray(0,5).toString(),'%PDF-');
 await page.screenshot({path:'test-results/rebuild/booking-confirmed.png'});
 await page.getByRole('button',{name:'Запросить ранний заезд',exact:true}).click();await expect(page.locator('.parameters')).toContainText('Ранний заезд запрошен');await page.getByRole('button',{name:'Моя поездка',exact:true}).click();
 const before=(await storage(page)).booking.result.total;await page.getByRole('button',{name:'Индивидуальный трансфер +3 500 ₽',exact:false}).click();await expect(page.locator('.parameters')).toContainText('Индивидуальный трансфер');assert.equal((await storage(page)).selectedResult.total,before+3500);
 await page.getByRole('button',{name:'Моя поездка',exact:true}).click();await page.getByRole('button',{name:'Перенести на два дня позже'}).click();await expect.poll(async()=>(await storage(page)).preferences.startDate).toBe('2027-06-14');await expect(page.locator('.booked-banner')).toHaveCount(0);
});
await scenario('Parameter editor, reload persistence and empty catalog keep entered constraints',async page=>{
 await send(page,'В декабре из Москвы');await page.locator('.parameter').filter({hasText:'Когда'}).click();await page.getByLabel('Новое условие').fill('В июне');await page.getByRole('button',{name:'Обновить поездку',exact:true}).click();await expect.poll(async()=>(await storage(page)).preferences.month).toBe(6);await page.reload();await expect(page.locator('.parameter').first()).toContainText('Июнь');
 await send(page,'Бюджет до 5 тысяч');await expect(page.locator('.empty-state')).toBeVisible();assert.equal((await storage(page)).preferences.budget,5000);
});
await scenario('Welcome and working layout at 320–1920px, mobile chat and reduced motion',async page=>{
 for(const width of [1920,1440,1280,1024,768,390,375,320]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.setViewportSize({width:1440,height:900});await send(page,'В декабре из Москвы');
 for(const width of [1920,1440,1280,1024,768,390,375,320]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.setViewportSize({width:390,height:844});await send(page,'С нами собака');await expect(page.locator('.parameters')).toContainText('С питомцем');
 await page.getByRole('button',{name:'Чат',exact:false}).click();await expect(page.getByLabel('Ваше сообщение')).toBeVisible();await page.screenshot({path:'test-results/rebuild/mobile-chat.png'});
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.send-button').evaluate(e=>getComputedStyle(e).transitionDuration),'0s');
});
await writeFile('test-results/e2e-report.json',JSON.stringify(report,null,2));await browser.close();const failed=report.filter(r=>r.status!=='passed');console.log(`${report.length-failed.length}/${report.length} browser scenarios passed`);if(failed.length)process.exitCode=1;
