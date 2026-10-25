"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Ban, BookOpen, EyeOff, FileText, Gavel, MessagesSquare, Network, Search, ShieldCheck, type LucideIcon } from "lucide-react";
import { findingStyles } from "@/lib/landing-data";
import { deriveRoom, formatElapsed, type AgentId, type AgentStatus, type LoggedEvent } from "@/lib/review-room";
import { Finding } from "./finding-label";
import { receiptNavigate, usePolishMotion } from "./landing-chrome";

const icons: Record<AgentId, LucideIcon> = { parser: FileText, hidden: EyeOff, claims: Network, resolver: Search, retraction: Ban, source: BookOpen, verifier: ShieldCheck, CLAIMS: MessagesSquare, METHODS: MessagesSquare, EVIDENCE: MessagesSquare, chair: Gavel };
const pills: Record<AgentStatus, [string, string]> = { QUEUED: ["Queued", "checking"], WORKING: ["Working", "working"], DONE: ["Done", "sage"], FLAGGED: ["Flagged", "red"], NEEDS_REVIEW: ["Needs review", "blue"] };
const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

// The live check as a room of agents. Everything shown is derived from received events; the only clocks are the elapsed
// display and the 3s hand-off to the report, which waits for the `done` event and yields to any reader interaction.
export function ReviewRoom({ id, log, autoNavigate = true }: { id: string; log: LoggedEvent[]; autoNavigate?: boolean }) {
  const reduced = usePolishMotion(), router = useRouter();
  const [now, setNow] = useState(() => Date.now()), [average, setAverage] = useState<number | null>(null), [interacted, setInteracted] = useState(false);
  const room = useMemo(() => deriveRoom(log, now), [log, now]);
  const href = `/report/${encodeURIComponent(id)}`, doneRef = useRef(false);
  useEffect(() => {
    if (room.done || !log.length) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [room.done, log.length]);
  // Ask for the historical average only for a run that is still in progress.
  const live = log.length > 0 && !room.done;
  useEffect(() => {
    if (!live) return;
    const abort = new AbortController();
    fetch(`${base}/status`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(5000)]) }).then(r => r.ok ? r.json() : null).then(data => { const avg = Number(data?.avg_duration_seconds); if (Number.isFinite(avg) && avg > 0) setAverage(avg); }).catch(() => {});
    return () => abort.abort();
  }, [live]);
  useEffect(() => {
    if (!room.done || doneRef.current) return;
    doneRef.current = true;
    const stop = () => setInteracted(true), opts = { once: true, passive: true } as const;
    addEventListener("wheel", stop, opts); addEventListener("touchmove", stop, opts); addEventListener("keydown", stop, opts); document.addEventListener("pointermove", stop, opts);
  }, [room.done]);
  useEffect(() => {
    if (!room.done || interacted || !autoNavigate) return;
    const timer = setTimeout(() => receiptNavigate(router.push, href), 3000);
    return () => clearTimeout(timer);
  }, [room.done, interacted, autoNavigate, router, href]);
  const remaining = average != null && !room.done ? Math.max(0, average - room.elapsed) : null;
  const ratio = room.progress.total ? room.progress.completed / room.progress.total : 0;
  return <section className="review-room" aria-label="Review room" data-done={room.done}>
    <header className="room-top">
      <div><p className="eyebrow">Review room</p><h1>{room.title ?? "Reading your paper…"}</h1></div>
      <div className="room-meter">
        <div className="room-progress" role="progressbar" aria-label="Stages completed" aria-valuemin={0} aria-valuemax={room.progress.total ?? undefined} aria-valuenow={room.progress.completed}><motion.span initial={false} animate={{ scaleX: room.done ? 1 : ratio }} transition={{ duration: reduced ? 0 : .3 }} /></div>
        <p><span className="room-mono">{room.progress.completed} / {room.progress.total ?? "…"} stages</span><span className="room-mono" aria-label="Elapsed time">{formatElapsed(room.elapsed)}</span>{remaining != null && <span>≈ {formatElapsed(remaining)} remaining <em>(estimate from past runs)</em></span>}</p>
      </div>
    </header>
    <AnimatePresence>{room.done && <motion.div className="room-done" role="status" initial={reduced ? false : { opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3 }}>
      <p><strong>Review complete</strong> · {formatElapsed(room.elapsed)}{!interacted && autoNavigate && <span className="room-handoff"> · opening the report…</span>}</p>
      <Link className="pill-button" href={href}>Open report <ArrowRight size={15} aria-hidden /></Link>
    </motion.div>}</AnimatePresence>
    <div className="room-grid">
      <ol className="room-agents" aria-label="Agents">{room.agents.map(agent => {
        const Icon = icons[agent.id], [pill, tone] = pills[agent.status];
        return <li key={agent.id} id={`agent-${agent.id}`} tabIndex={-1} className="agent-card" data-agent={agent.id} data-status={agent.status}>
          <header><Icon size={17} aria-hidden /><h2>{agent.name}</h2>
            <span className={`status-pill ${tone}`}>{agent.status === "WORKING" && !reduced && <motion.i aria-hidden className="pill-pulse" initial={{ scale: 1, opacity: .45 }} animate={{ scale: 2.4, opacity: 0 }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }} />}{pill}</span></header>
          {agent.detail && <p className="agent-detail">{agent.detail}</p>}
          <p className="agent-current">{agent.status === "NEEDS_REVIEW" ? agent.reason : agent.current ?? (agent.status === "QUEUED" ? "Waiting for its first event" : " ")}</p>
          {agent.total != null ? <div className="agent-count"><span className="agent-bar"><motion.i initial={false} animate={{ scaleX: agent.total ? agent.done / agent.total : 0 }} transition={{ duration: reduced ? 0 : .25 }} /></span><span className="room-mono">{agent.done} / {agent.total}</span></div> : <div className="agent-count"><span className="room-mono">{agent.done} finding{agent.done === 1 ? "" : "s"}</span></div>}
          <p className="agent-finding">{agent.finding ?? " "}</p>
          {agent.model && <span className="agent-model">{agent.model}</span>}
        </li>;
      })}</ol>
      <div className="room-side">
        <figure className="room-paper hero-paper" aria-label="References as they resolve">
          <p className="paper-title">{room.title ?? "Untitled manuscript"}</p>
          <p className="paper-references-heading">References</p>
          <ol className="room-slots">{room.slots.map(slot => <li key={slot.id} className="paper-slot hero-slot" data-filled={!!slot.chip} data-chip={slot.chip ?? undefined}>
            <span className="paper-slot-number">[{slot.index + 1}]</span>
            <span className="paper-slot-body"><motion.span className="paper-slot-fill" initial={false} animate={{ opacity: slot.chip ? 1 : .55 }} transition={{ duration: reduced ? 0 : .15 }}>
              {slot.chip && <span aria-hidden className="paper-slot-bar" style={{ background: `var(--finding-bar-${slot.chip}, ${findingStyles[slot.chip].color})` }} />}
              <span className="paper-slot-ref"><strong>{slot.label}</strong></span>
              {slot.chip ? <Finding chip={slot.chip} /> : <span className="room-pending">Resolving…</span>}
            </motion.span></span>
          </li>)}</ol>
          {room.done && <ul className="hero-tally room-tally" aria-label="Findings by reference">{room.tally.map(({ chip, count }, i) => <motion.li key={chip} initial={reduced ? false : { opacity: 0, scale: .9 }} animate={{ opacity: 1, scale: reduced ? 1 : [.9, 1.06, 1] }} transition={{ duration: .16, delay: reduced ? 0 : .2 + i * .09 }} style={{ color: `var(--finding-${chip}, ${findingStyles[chip].text})`, borderColor: `var(--finding-bar-${chip}, ${findingStyles[chip].color})` }}>{count} {findingStyles[chip].short}</motion.li>)}</ul>}
        </figure>
        <section className="room-feed" aria-label="Findings feed"><h2>Findings, as they arrive</h2>
          <ol aria-live="polite">{[...room.feed].reverse().slice(0, 40).map(row => <motion.li key={row.seq} initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .22 }}>
            <button type="button" onClick={() => { const card = document.getElementById(`agent-${row.agent}`); card?.scrollIntoView({ block: "center", behavior: reduced ? "instant" : "smooth" }); card?.focus({ preventScroll: true }); }}>
              <span className="room-mono">{formatElapsed(Math.max(0, (row.at - (log[0]?.receivedAt ?? row.at)) / 1000))}</span><span className="feed-text">{row.text}</span>{row.chip && <Finding chip={row.chip} />}
            </button>
          </motion.li>)}</ol>
        </section>
      </div>
    </div>
  </section>;
}
