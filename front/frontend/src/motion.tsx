import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { MotionConfig } from 'motion/react';

export const timing = { feedback: .15, message: .21, toast: .22, modal: .22, card: .30, drawer: .32, exit: .15, slide: .75 };
export const easeOut = [.16, 1, .3, 1] as const;
const MotionEnabled = createContext(false);
export function MotionSettings({ children }: { children: ReactNode }) {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion:reduce)').matches);
  const [visible, setVisible] = useState(!document.hidden);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion:reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const update = () => { setVisible(!document.hidden); document.documentElement.dataset.pageHidden = String(document.hidden); };
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    if (reduced || !visible) return;
    const reveal = (event: Event) => {
      const details = event.target;
      if (!(details instanceof HTMLDetailsElement) || !details.open) return;
      for (const child of details.children) if(child.tagName !== 'SUMMARY') child.animate([{opacity:0,transform:'translateY(-4px)'},{opacity:1,transform:'none'}],{duration:180,easing:'cubic-bezier(.16,1,.3,1)'});
    };
    document.addEventListener('toggle', reveal, true);
    return () => document.removeEventListener('toggle', reveal, true);
  }, [reduced, visible]);
  return <MotionEnabled.Provider value={!reduced && visible}><MotionConfig reducedMotion={reduced ? 'always' : 'never'} transition={{ duration: timing.card, ease: easeOut }}>{children}</MotionConfig></MotionEnabled.Provider>;
}
export const useMotionEnabled = () => useContext(MotionEnabled);
