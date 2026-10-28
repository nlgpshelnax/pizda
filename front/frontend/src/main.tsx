import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './workspace.css';
import './motion.css';
import { MotionSettings } from './motion';
import { Toasts } from './components/Toast';
createRoot(document.getElementById('root')!).render(<StrictMode><MotionSettings><App /><Toasts /></MotionSettings></StrictMode>);
