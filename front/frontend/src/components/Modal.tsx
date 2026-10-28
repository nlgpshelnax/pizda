import { useEffect, useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { usePresence } from 'motion/react';
import { X } from 'lucide-react';
import { timing, useMotionEnabled } from '../motion';
export function Modal({ title, onClose, children, wide = false, drawer = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; drawer?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [present, remove] = usePresence();
  const enabled = useMotionEnabled();
  const openingMotion = useRef(enabled);
  useLayoutEffect(() => { const dialog = ref.current; dialog?.showModal(); dialog?.querySelector<HTMLElement>('[data-modal-autofocus]')?.focus(); return () => dialog?.close(); }, []);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!enabled || (present && !openingMotion.current)) { if (!present) remove?.(); return; }
    const mobile = window.matchMedia('(max-width:767px)').matches;
    const offset = drawer ? (mobile ? 'translateY(24px)' : 'translateX(48px)') : 'translateY(8px) scale(.97)';
    const frames = [{ opacity: 0, transform: offset }, { opacity: 1, transform: 'none' }];
    const animation = dialog.animate(present ? frames : [...frames].reverse(), { duration: (present ? drawer ? timing.drawer : timing.modal : timing.exit) * 1000, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'both' });
    const backdrop = dialog.animate([{ backgroundColor: 'rgb(47 65 86 / 0)' }, { backgroundColor: 'rgb(47 65 86 / .45)' }], { pseudoElement: '::backdrop', duration: timing.modal * 1000, direction: present ? 'normal' : 'reverse', fill: 'both' });
    animation.finished.then(() => { if (!present) remove?.(); }).catch(() => {});
    return () => { animation.cancel(); backdrop.cancel(); };
  }, [present, enabled, drawer, remove]);
  return <dialog className={`modal ${wide ? 'modal-wide' : ''} ${drawer ? 'modal-drawer' : ''}`} data-exiting={!present} ref={ref} aria-label={title} onKeyDown={e=>{if(!present)e.preventDefault();}} onCancel={e => { e.preventDefault(); if (present) onClose(); }} onClick={e => { if (present && e.target === ref.current) onClose(); }}>
    <div className="modal-inner"><div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Закрыть окно"><X size={20} /></button></div>{children}</div>
  </dialog>;
}
