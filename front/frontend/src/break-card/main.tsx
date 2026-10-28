import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { JourneyCard } from '../components/JourneyCard';
import { trips } from '../data/trips';
import type { Preferences, RankedTrip } from '../types';
import '../styles.css';
import '../workspace.css';

// Fixtures only: the harness does not use or mutate the user's session.
const preferences: Preferences = {
  slots: { when: { value: 'июнь', status: 'YES' }, destination: { value: 'Европа', status: 'Vague' }, origin: { value: 'Москва', status: 'YES' }, purpose: { value: 'прогулки', status: 'YES' } },
  startDate: '2027-06-12', month: 6, nights: 6, nightsEstimated: false, guests: 1, guestsEstimated: false,
  starsStrict: false, visaFree: false, visaStrict: false, pet: false, petStrict: true,
  seaOnly: false, poolAccepted: false, central: false, earlyCheckin: false, privateTransfer: false, purposes: ['walks', 'culture'],
};
const trip = trips.find(item => item.id === 'novisad')!;
const base: RankedTrip = { trip, costs: trip.costs, total: 46900, score: 85, reasons: ['Архитектура, прогулки'], compromises: [] };
const long: RankedTrip = { ...base, compromises: ['«Хочу неспешно гулять по историческим кварталам, попробовать местную кухню и посетить небольшие музеи рядом с отелем» не подтверждено в каталоге; показан близкий тип отдыха'] };
const unbroken: RankedTrip = { ...base, compromises: ['«достопримечательностивокругисторическогоцентраипрогулкивдольнабережной» не подтверждено в каталоге'] };

function Card({result = base, busy = false, initialSaved = false, initialSelected = false, recommended = false}: {result?: RankedTrip; busy?: boolean; initialSaved?: boolean; initialSelected?: boolean; recommended?: boolean}) {
  const [saved, setSaved] = useState(initialSaved);
  const [selected, setSelected] = useState(initialSelected);
  return <JourneyCard result={result} preferences={preferences} recommended={recommended} selected={selected} saved={saved} busy={busy} onSave={() => setSaved(!saved)} onDetails={() => {}} onChoose={() => setSelected(true)} />;
}
function Scenario({label, width, children}: {label: string; width?: number; children: React.ReactNode}) {
  return <section style={{marginBlock: '24px'}}><h2 style={{fontSize: '16px', marginBottom: '10px'}}>{label}</h2><div style={{width, maxWidth: '100%'}}>{children}</div></section>;
}
function App() {
  return <div className="app-layout"><main className="workspace" style={{padding: '24px'}}>
    <h1>Стресс-проверка карточки поездки</h1>
    <p>Проверьте также управление с клавиатуры, масштаб страницы и уменьшение движения.</p>
    <Scenario label="Обычное предложение" width={420}><Card recommended /></Scenario>
    <Scenario label="Контейнер 320 px" width={320}><Card recommended /></Scenario>
    <Scenario label="Сжатие соседним элементом сетки" width={500}><div style={{display:'grid',gridTemplateColumns:'minmax(0, 1fr) 150px',gap:'12px'}}><Card /><span>Соседний элемент</span></div></Scenario>
    <Scenario label="Широкий контейнер" width={1000}><Card /></Scenario>
    <Scenario label="Поездка выбрана и сохранена" width={420}><Card initialSelected initialSaved /></Scenario>
    <Scenario label="Подбор занят: выбор недоступен" width={420}><Card busy /></Scenario>
    <Scenario label="Длинное пожелание в компромиссе" width={320}><Card result={long} /></Scenario>
    <Scenario label="Пожелание без пробелов" width={320}><Card result={unbroken} /></Scenario>
  </main></div>;
}
createRoot(document.getElementById('root')!).render(<App />);
