import { Composer } from './Composer';
import { WelcomeSlideshow } from './WelcomeSlideshow';

interface Props { onSend:(text:string)=>void; busy:boolean }
const examples = [
  { label:'Прогулки в Португалии', query:'Хочу прогулки в Португалии' },
  { label:'Архитектура в Италии', query:'Хочу архитектуру в Италии' },
  { label:'Горы и SPA', query:'Хочу горы и SPA' },
];

export function Welcome({onSend,busy}:Props) {
  return <main className="welcome" id="main">
    <div className="welcome-hero">
      <section className="welcome-start">
        <h1>Куда хотите отправиться?</h1>
        <p>Опишите поездку. Соберём дорогу, отель и трансфер в один план.</p>
        <Composer onSend={onSend} busy={busy} large/>
        <p className="welcome-hint">Можно начать с месяца и города отправления. Остальное уточним в диалоге.</p>
        <div className="welcome-examples" aria-label="Примеры запросов">
          <span>Например</span>
          <div>{examples.map(example=><button key={example.label} onClick={()=>onSend(example.query)} disabled={busy}>{example.label}</button>)}</div>
        </div>
      </section>
      <WelcomeSlideshow/>
    </div>
    <footer className="welcome-footer">Демо-каталог из 15 вымышленных поездок. Цены и рейсы учебные.</footer>
  </main>;
}
