import { mkdir, writeFile } from 'node:fs/promises';
const photos = {
  'coast': 'photo-1516483638261-f4dbaf036963',
  'barcelona': 'photo-1539037116277-4db20889f2d4',
  'paris': 'photo-1502602898657-3e91760cbb34',
  'mountains': 'photo-1519681393784-d120267933ba',
};
await mkdir('public/images', {recursive:true});
await Promise.all(Object.entries(photos).map(async ([name, id]) => {
  const response = await fetch(`https://images.unsplash.com/${id}?auto=format&fit=crop&w=1600&q=85`);
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  await writeFile(`public/images/${name}.jpg`, Buffer.from(await response.arrayBuffer()));
  console.log(`Saved ${name}`);
}));
await mkdir('public/fonts', {recursive:true});
const response = await fetch('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Prata&display=swap', {
  headers: { 'User-Agent': 'Mozilla/5.0 AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36' },
});
if (!response.ok) throw new Error(`Fonts: ${response.status}`);
let css = await response.text();
const urls = [...new Set([...css.matchAll(/url\((https:[^)]+)\)/g)].map(m => m[1]))];
for (let i=0; i<urls.length; i++) {
  const font = await fetch(urls[i]);
  if (!font.ok) throw new Error(`Font file: ${font.status}`);
  await writeFile(`public/fonts/font-${i}.woff2`, Buffer.from(await font.arrayBuffer()));
  css = css.replaceAll(urls[i], `/fonts/font-${i}.woff2`);
}
await writeFile('public/fonts/fonts.css', css);
console.log(`Saved ${urls.length} font subsets`);
