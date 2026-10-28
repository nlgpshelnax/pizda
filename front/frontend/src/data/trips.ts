import type { Trip } from '../types';

type Entry = Pick<Trip, 'id' | 'country' | 'city' | 'title' | 'subtitle' | 'purposes' | 'image'> & Partial<Trip> & {
  hotelName: string; price: number; stars?: number; petFriendly?: boolean;
};
const summer = [5, 6, 7, 8, 9];
const all = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const entries: Entry[] = [
  { id: 'madeira', country: 'Португалия', city: 'Фуншал', region: 'Мадейра', destinationKeys: ['Мадейра', 'Португалия'], airport: 'FNC', title: 'Остров, где можно выдохнуть', subtitle: 'Мадейра · океан, сады и медленные утра', hotelName: 'Quinta da Brisa', price: 104500, image: 'sea', purposes: ['spa', 'walks', 'beach'], heatedPool: true, petFriendly: true, activities: ['Прогулка по ботаническому саду', 'Тропы вдоль левад', 'Отдых у подогреваемого бассейна'], flightHours: '10 ч 40 мин', stop: 'Стамбул', transferMinutes: 35 },
  { id: 'lisbon', country: 'Португалия', city: 'Лиссабон', airport: 'LIS', title: 'В ритме солнечного Лиссабона', subtitle: 'Старинные трамваи, азулежу и вкус океана', hotelName: 'Casa do Tejo', price: 87600, image: 'lisbon', purposes: ['culture', 'walks'], petFriendly: true, central: true, activities: ['Прогулка по Алфаме', 'Музей азулежу', 'Паштел-де-ната у набережной'] },
  { id: 'tenerife', country: 'Испания', city: 'Адехе', region: 'Тенерифе', destinationKeys: ['Тенерифе', 'Испания'], airport: 'TFS', title: 'Немного ближе к солнцу', subtitle: 'Тенерифе · вулканический остров и Атлантика', hotelName: 'Costa Serena', price: 112800, image: 'sea', purposes: ['beach', 'spa', 'walks'], heatedPool: true, warmSea: [6, 7, 8, 9, 10], flightHours: '11 ч 20 мин', transferMinutes: 45, activities: ['Национальный парк Тейде', 'Прибрежный променад', 'Бассейн с подогревом'] },
  { id: 'barcelona', country: 'Испания', city: 'Барселона', airport: 'BCN', title: 'Влюбиться в детали Барселоны', subtitle: 'Архитектура Гауди и город у моря', hotelName: 'Patio del Sol', price: 98600, image: 'barcelona', purposes: ['culture', 'walks', 'beach'], petFriendly: true, central: true, warmSea: summer, activities: ['Саграда-Фамилия', 'Квартал Эшампле', 'Закат у Барселонеты'] },
  { id: 'rome', country: 'Италия', city: 'Рим', airport: 'FCO', title: 'Рим без спешки', subtitle: 'Античные улицы и итальянское dolce far niente', hotelName: 'Palazzo Alba', stars: 5, price: 149800, image: 'venice', purposes: ['culture', 'walks'], central: true, activities: ['Римский форум', 'Музеи Ватикана', 'Ужин в Трастевере'] },
  { id: 'florence', country: 'Италия', city: 'Флоренция', airport: 'FLR', title: 'Искусство жить по-тоскански', subtitle: 'Галереи, уютные площади и тосканская кухня', hotelName: 'Casa Fiorentina', price: 109600, image: 'coast', purposes: ['culture', 'walks'], central: true, petFriendly: true, activities: ['Галерея Уффици', 'Понте-Веккьо', 'Смотровая площадь Микеланджело'] },
  { id: 'nice', country: 'Франция', city: 'Ницца', airport: 'NCE', title: 'Ваше место на Лазурном берегу', subtitle: 'Лазурное море и неспешные прогулки', hotelName: 'Maison Azur', price: 123400, image: 'coast', purposes: ['beach', 'walks', 'culture'], petFriendly: true, warmSea: summer, activities: ['Английская набережная', 'Старый город', 'Поездка в Эз'] },
  { id: 'paris', country: 'Франция', city: 'Париж', airport: 'CDG', title: 'Париж, каким вы его представляли', subtitle: 'Музеи, булочные и утро на левом берегу', hotelName: 'Atelier Saint-Germain', price: 138900, image: 'paris', purposes: ['culture', 'walks'], central: true, activities: ['Музей Орсе', 'Прогулка вдоль Сены', 'Люксембургский сад'] },
  { id: 'belgrade', country: 'Сербия', city: 'Белград', airport: 'BEG', title: 'Выходные, которые стали отпуском', subtitle: 'Тёплые встречи на берегах Савы и Дуная', hotelName: 'Sava House', price: 58400, image: 'lisbon', purposes: ['walks', 'culture'], petFriendly: true, central: true, visaForRU: 'free', stop: 'Без пересадок', flightHours: '3 ч 20 мин', activities: ['Калемегдан', 'Кафе в Дорчоле', 'Набережная Савы'] },
  { id: 'novisad', country: 'Сербия', city: 'Нови-Сад', airport: 'BEG', title: 'Маленький город, большой отдых', subtitle: 'Дунайские набережные и уютные кофейни', hotelName: 'Danube Garden', stars: 3, price: 46900, image: 'venice', purposes: ['walks', 'culture'], petFriendly: true, central: true, visaForRU: 'free', stop: 'Без пересадок', flightHours: '3 ч 20 мин', transferMinutes: 75, activities: ['Петроварадинская крепость', 'Дунайский парк', 'Гастрономическая прогулка'] },
  { id: 'kopaonik', country: 'Сербия', city: 'Копаоник', airport: 'BEG', title: 'Время для снега и тишины', subtitle: 'Сербские горы, хвойный воздух и SPA', hotelName: 'Pine Lodge', price: 82400, image: 'mountains', purposes: ['mountains', 'spa'], heatedPool: true, seasons: [12, 1, 2, 3], visaForRU: 'free', stop: 'Без пересадок', flightHours: '3 ч 20 мин', transferMinutes: 190, activities: ['Горные склоны', 'Прогулка по хвойному лесу', 'Термальная зона'], arrival: '10:10', returnDeparture: '18:30' },
  { id: 'budapest', country: 'Венгрия', city: 'Будапешт', airport: 'BUD', title: 'Город, который согревает', subtitle: 'Термальные купальни и огни Дуная', hotelName: 'Thermal House', price: 79800, image: 'venice', purposes: ['spa', 'culture', 'walks'], heatedPool: true, central: true, activities: ['Купальни Сечени', 'Рыбацкий бастион', 'Вечерняя набережная'] },
  { id: 'innsbruck', country: 'Австрия', city: 'Инсбрук', region: 'Альпы', destinationKeys: ['Альпы', 'Австрия'], airport: 'INN', title: 'Высоко в горах, далеко от суеты', subtitle: 'Альпийские вершины и тихий отдых в шале', hotelName: 'Alpine Haze', stars: 5, price: 174800, image: 'mountains', purposes: ['mountains', 'spa'], petFriendly: true, heatedPool: true, seasons: [12, 1, 2, 3, 6, 7, 8], activities: ['Канатная дорога Нордкетте', 'Прогулки в горах', 'Панорамный бассейн'] },
  { id: 'kotor', country: 'Черногория', city: 'Котор', airport: 'TIV', title: 'Между горами и морем', subtitle: 'Которская бухта, старые улочки и свежий воздух', hotelName: 'Casa di Boka', price: 69800, image: 'coast', purposes: ['beach', 'walks', 'mountains'], petFriendly: true, warmSea: summer, visaForRU: 'free', activities: ['Старый город Котора', 'Прогулка по бухте', 'Поездка в Пераст'] },
  { id: 'crete', country: 'Греция', city: 'Ханья', region: 'Крит', destinationKeys: ['Крит', 'Греция'], airport: 'CHQ', title: 'Островное счастье на Крите', subtitle: 'Средиземное море и солнечные дни', hotelName: 'Asteri Bay', stars: 5, price: 137000, image: 'greece', purposes: ['beach', 'spa', 'culture'], heatedPool: true, warmSea: summer, seasons: [4, 5, 6, 7, 8, 9, 10], activities: ['Венецианская гавань', 'Пляж Элафониси', 'Критская гастрономия'] },
];

export const trips: Trip[] = entries.map(e => {
  const transport = e.visaForRU === 'free' ? 24500 : 46000;
  const transfer = e.transferMinutes && e.transferMinutes > 60 ? 8500 : 4500;
  const extras = e.stars === 5 ? 10000 : 6000;
  return {
    region: e.city, destinationKeys: [e.city, e.country], airport: 'XXX',
    seasons: all, warmSea: [], heatedPool: false, central: false, visaForRU: 'required',
    visaNote: 'Учебная визовая справка для паспорта РФ. Въезд зависит от гражданства, срока поездки и документов; необходима актуальная проверка.',
    costs: { transport, hotel: e.price - transport - transfer - extras, transfer, extras },
    flightHours: '7 ч 40 мин', transferMinutes: 40, stop: 'Стамбул', arrival: '13:10', outbound: '06:30', returnDeparture: '16:30',
    activities: ['Прогулки по городу', 'Знакомство с местной кухней', 'Свободный день'],
    risk: 'Рейсы, наличие номера, правила въезда и стоимость требуют подтверждения.',
    ...e,
    image: ['barcelona', 'paris'].includes(e.id) ? e.image : e.id,
    hotel: {
      name: e.hotelName, stars: e.stars ?? 4, rating: '9,1',
      description: e.heatedPool ? 'Камерный отель с подогреваемым бассейном и спокойной атмосферой. Номер Standard, завтрак включён.' : 'Небольшой уютный отель, откуда удобно знакомиться с городом. Номер Standard, завтрак включён.',
      amenities: ['Wi-Fi', 'Завтраки', ...(e.heatedPool ? ['Бассейн с подогревом'] : ['Кондиционер']), ...(e.petFriendly ? ['Можно с питомцем'] : [])],
      meals: 'Завтраки', pets: e.petFriendly ?? false, checkin: '14:00', checkinUntil: '23:59', checkout: '11:00',
    },
  };
});
