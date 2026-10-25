"use client";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { animate, motion, useInView } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
const ease = [.2,.7,.2,1] as const;
export function Reveal({ children, className = "", image = false, delay = 0 }: { children: ReactNode; className?: string; image?: boolean; delay?: number }) {
 const reduced = usePolishMotion();
 return <motion.div className={className} data-reveal initial={reduced ? false : image ? { opacity:0,scale:.985 } : { opacity:0,y:12 }} whileInView={{opacity:1,y:0,scale:1}} viewport={{once:true,amount:.2}} transition={{duration:reduced ? 0 : image ? .5 : .36, ease, delay:reduced ? 0 : delay}}>{children}</motion.div>;
}
export function CountOnce({ value }: { value: number }) {
 const ref = useRef<HTMLSpanElement>(null), visible = useInView(ref,{once:true,amount:.2}), reduced = usePolishMotion();
 const [count,setCount] = useState(value);
 useEffect(() => {
  if (!visible || reduced) return;
  const control = animate(0,value,{duration:.6,ease:"easeOut",onUpdate:n => setCount(Math.round(n))});
  return () => control.stop();
 },[visible,reduced,value]);
 return <span ref={ref} className="count-once" role="img" style={{minWidth:`${String(value).length}ch`}} aria-label={String(value)}><span aria-hidden>{reduced ? value : visible ? count : 0}</span></span>;
}
const LinkContext=createContext(false), FlashContext=createContext(0), ShownContext=createContext(true);
export function LinkedNote({ children, className }: { children: ReactNode; className: string }) {
 const [active,setActive]=useState(false), [flash,setFlash]=useState(0);
 return <LinkContext.Provider value={active}><FlashContext.Provider value={flash}><div className={className} onClick={e => { if ((e.target as HTMLElement).closest(".margin-note")) setFlash(n => n+1); }} onMouseOver={e => setActive(!!(e.target as HTMLElement).closest(".margin-note,.excerpt-text,.reader-paragraph"))} onMouseLeave={() => setActive(false)} onFocusCapture={() => setActive(true)} onBlurCapture={e => {if(!e.currentTarget.contains(e.relatedTarget))setActive(false);}}>{children}</div></FlashContext.Provider></LinkContext.Provider>;
}
// cl-flash: clicking a note tints its paper line in the accent, then fades out.
export function FlashTint() { const flash=useContext(FlashContext),reduced=usePolishMotion();return flash && !reduced ? <motion.span key={flash} aria-hidden className="note-tint" initial={{opacity:.22}} animate={{opacity:0}} transition={{duration:.9,ease:"easeOut"}} /> : null; }
// Margin notes in one figure stagger in 80ms apart the first time the figure is seen.
export function ExcerptFigure({ children, className }: { children: ReactNode; className: string }) {
 const ref=useRef<HTMLElement>(null), seen=useInView(ref,{once:true,amount:.2}), reduced=usePolishMotion();
 return <ShownContext.Provider value={reduced||seen}><figure ref={ref} className={className}>{children}</figure></ShownContext.Provider>;
}
export function NoteReveal({ children, index }: { children: ReactNode; index: number }) {
 const shown=useContext(ShownContext),reduced=usePolishMotion();
 return <motion.div className="note-reveal" initial={false} animate={shown?{opacity:1,y:0}:{opacity:0,y:8}} transition={shown&&!reduced?{duration:.22,ease,delay:.1+index*.08}:{duration:0}}>{children}</motion.div>;
}
export function NoteTint() { const active=useContext(LinkContext),reduced=usePolishMotion();return <motion.span aria-hidden className="note-tint" initial={false} animate={{opacity:active?.09:0}} transition={{duration:reduced?0:.16}} />; }
export function PenUnderline() {const reduced=usePolishMotion();return <motion.span aria-hidden className="pen-underline" initial={reduced?false:{scaleX:0}} whileInView={{scaleX:1}} viewport={{once:true,amount:.2}} transition={{duration:reduced?0:.3,ease}} />;}
