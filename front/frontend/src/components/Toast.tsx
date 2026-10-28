import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, Info, X } from 'lucide-react';
import { easeOut, timing, useMotionEnabled } from '../motion';
type Notice = { text: string; error?: boolean };
export const notify = (text: string, error = false) => window.dispatchEvent(new CustomEvent<Notice>('odin-notice', { detail: { text, error } }));
export function Toasts() {
  const [notice, setNotice] = useState<Notice>();
  const [paused, setPaused] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const enabled = useMotionEnabled();
  useEffect(() => {
    const receive = (event: Event) => setNotice((event as CustomEvent<Notice>).detail);
    window.addEventListener('odin-notice', receive);
    return () => window.removeEventListener('odin-notice', receive);
  }, []);
  useEffect(() => {
    if (notice && host.current && !host.current.matches(':popover-open')) host.current.showPopover?.();
  }, [notice]);
  useEffect(() => {
    if (!notice || paused || document.hidden) return;
    const timeout = window.setTimeout(() => setNotice(undefined), 5000);
    return () => window.clearTimeout(timeout);
  }, [notice, paused, enabled]);
  return <div ref={host} popover="manual" className="toast-host" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false); }}>
    <AnimatePresence onExitComplete={() => { if(!notice) host.current?.hidePopover?.(); }}>{notice && <motion.div key={notice.text} className={`toast ${notice.error ? 'toast-error' : ''}`} role={notice.error ? 'alert' : 'status'} initial={enabled ? { opacity: 0, x: 16 } : false} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: enabled ? 6 : 0 }} transition={{ duration: enabled ? timing.toast : 0, ease: easeOut }}>
      {notice.error ? <Info size={18} aria-hidden="true"/> : <Check size={18} aria-hidden="true"/>}<p>{notice.text}</p><button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setNotice(undefined)}><X size={17}/></button>
    </motion.div>}</AnimatePresence>
  </div>;
}
