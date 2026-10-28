import { CircleHelp, Compass, Plus } from 'lucide-react';
export function Brand() { return <span className="brand"><span className="brand-mark">О!</span><span>дин запрос</span></span>; }
interface Props { working: boolean; hasBooking?: boolean; onReset: () => void; onHelp: () => void; onTrips: () => void }
export function Header({ working, hasBooking, onReset, onHelp, onTrips }: Props) {
  return <header className="header"><button className="brand-button" onClick={onTrips} aria-label={working ? 'О!дин запрос, открыть поездки' : 'О!дин запрос, перейти к полю запроса'}><Brand /></button>
    <nav aria-label="Основная навигация"><span className="demo-badge">Демо</span><button className="help-button" onClick={onHelp} aria-label="Как это работает"><CircleHelp size={17} /><span>Справка</span></button>{hasBooking && <button className="nav-link booking-nav" onClick={onTrips}><Compass size={16} />Моя поездка</button>}
    {working && <button className="new-trip" onClick={onReset}><Plus size={17} /> Новая поездка</button>}
    </nav>
  </header>;
}
