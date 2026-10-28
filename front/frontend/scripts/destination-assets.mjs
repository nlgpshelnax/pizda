import { writeFile } from 'node:fs/promises';
const destinations = { lisbon:'Lisbon', belgrade:'Belgrade', novisad:'Novi Sad', florence:'Florence', budapest:'Budapest', kotor:'Kotor', nice:'Nice', crete:'Chania', tenerife:'Adeje', kopaonik:'Kopaonik', innsbruck:'Innsbruck' };
const credits = [];
for (const [name,title] of Object.entries(destinations)) {
  const summary = await fetch('https://en.wikipedia.org/api/rest_v1/page/summary/'+encodeURIComponent(title)).then(r=>r.json());
  const original = summary.originalimage.source.split('?')[0];
  const file = decodeURIComponent(original.includes('/thumb/') ? original.split('/').at(-2) : original.split('/').at(-1));
  const query = new URL('https://commons.wikimedia.org/w/api.php');
  query.search = new URLSearchParams({action:'query',titles:'File:'+file,prop:'imageinfo',iiprop:'url|extmetadata',iiurlwidth:'1600',format:'json'});
  const infoResponse = await fetch(query).then(r=>r.json());
  const info = Object.values(infoResponse.query.pages)[0].imageinfo[0];
  const response = await fetch(info.thumburl || info.url);
  if (!response.ok) throw new Error(`${title}: ${response.status}`);
  await writeFile(`public/images/${name}.jpg`,Buffer.from(await response.arrayBuffer()));
  const strip = value => value?.replace(/<[^>]+>/g,'').replace(/\s+/g,' ').trim() || '';
  credits.push({ name, title, source:info.descriptionurl, author:strip(info.extmetadata.Artist?.value), license:strip(info.extmetadata.LicenseShortName?.value), licenseUrl:info.extmetadata.LicenseUrl?.value });
  console.log(`Saved ${name}`);
}
const additions = { madeira:'photo-1628413283166-a7666966d26b', rome:'photo-1572319805438-61eeede8e74d' };
for(const [name,id] of Object.entries(additions)) {
  const response=await fetch(`https://images.unsplash.com/${id}?auto=format&fit=crop&w=1600&q=85`);
  if(!response.ok) throw new Error(`${name}: ${response.status}`);
  await writeFile(`public/images/${name}.jpg`,Buffer.from(await response.arrayBuffer()));
}
await writeFile('src/data/photo-credits.json',JSON.stringify(credits,null,2));
await writeFile('docs/PHOTO-CREDITS.md','# Источники фотографий\n\nФотографии направлений, не изображения вымышленных отелей. Файлы сохранены локально; изображение отображается с кадрированием CSS, цвет не изменялся.\n\n'+credits.map(c=>`- **${c.title}** (${c.name}.jpg): ${c.author}. [Источник](${c.source}). [${c.license}](${c.licenseUrl}).`).join('\n')+'\n\nДругие фотографии: Unsplash. Список идентификаторов находится в scripts/download-assets.mjs и scripts/destination-assets.mjs. Мадейра: Colin Watts, https://unsplash.com/photos/C8e3LGjg3fc. Рим: William VanBuskirk, https://unsplash.com/photos/B_FylPoY0tg.\n');
