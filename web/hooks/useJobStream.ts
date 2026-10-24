"use client";
import { useEffect, useReducer } from "react";
import { decodeEvent, eventTypes, initialJob, jobReducer } from "@/lib/job-stream";

const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
export function useJobStream(id: string) {
  const [state, dispatch] = useReducer(jobReducer, initialJob);
  useEffect(() => {
    dispatch({ type: "reset" });
    const abort = new AbortController();
    let stream: EventSource | undefined, timer: ReturnType<typeof setTimeout> | undefined, failures = 0;
    const notice = (reason: string) => dispatch({ type: "notice", reason });
    async function snapshot() {
      const response = await fetch(`${base}/jobs/${encodeURIComponent(id)}`, { cache: "no-store", signal: AbortSignal.any([abort.signal, AbortSignal.timeout(10_000)]) });
      const data = await response.json();
      if (abort.signal.aborted) return true;
      if (!response.ok || !Array.isArray(data?.events)) throw new Error("Snapshot unavailable");
      dispatch({ type: "snapshot", events: data.events });
      return data.events.some((e: unknown) => decodeEvent(e)?.type === "done");
    }
    async function poll() {
      try { if (await snapshot()) return; }
      catch { if (!abort.signal.aborted) notice("CHECK_INCOMPLETE: snapshot unavailable. Retrying every 2 seconds."); }
      if (!abort.signal.aborted) timer = setTimeout(poll, 2000);
    }
    async function start() {
      if (process.env.NEXT_PUBLIC_MOCK === "1") {
        const response = await fetch("/fixtures/events/paper1.jsonl", { signal: abort.signal });
        if (!response.ok) throw new Error("Fixture unavailable");
        const events = (await response.text()).trim().split("\n").map((line, index) => ({ ...JSON.parse(line), at: index * 100 }));
        if (abort.signal.aborted) return;
        const key = `verres:mock:${id}`;
        let started = Date.now();
        try { const saved = Number(sessionStorage.getItem(key)); if (saved > 0 && saved <= started) started = saved; sessionStorage.setItem(key, String(started)); } catch { /* Replay still works without storage. */ }
        const elapsed = Date.now() - started;
        dispatch({ type: "snapshot", events: events.filter(e => e.at <= elapsed) });
        let index = events.findIndex(e => e.at > elapsed);
        const replay = () => {
          if (index < 0 || index >= events.length || abort.signal.aborted) return;
          const event = events[index];
          timer = setTimeout(() => { dispatch({ type: "snapshot", events: [event] }); index++; replay(); }, Math.max(0, started + event.at - Date.now()));
        };
        replay();
        return;
      }
      try { if (await snapshot()) return; }
      catch { if (!abort.signal.aborted) notice("CHECK_INCOMPLETE: initial snapshot unavailable. Recovering from the event stream."); }
      if (abort.signal.aborted) return;
      stream = new EventSource(`${base}/jobs/${encodeURIComponent(id)}/events`);
      for (const type of eventTypes) stream.addEventListener(type, (message) => {
        if (!(message instanceof MessageEvent)) return;
        try {
          const event = decodeEvent({ type, seq: Number(message.lastEventId), payload: JSON.parse(message.data) });
          if (!event) return notice("CHECK_INCOMPLETE: unreadable event; review continues.");
          failures = 0;
          dispatch({ type: "event", event });
          if (type === "done") stream?.close();
        } catch { notice("CHECK_INCOMPLETE: unreadable event; review continues."); }
      });
      stream.onerror = (event) => {
        if (event instanceof MessageEvent || abort.signal.aborted) return;
        if (++failures >= 3) { // Initial disconnect, then two failed native reconnects.
          stream?.close(); notice("Live connection interrupted. Checking snapshots every 2 seconds."); void poll();
        }
      };
    }
    void start().catch(() => { if (!abort.signal.aborted) notice("CHECK_INCOMPLETE: review could not be loaded."); });
    return () => { abort.abort(); stream?.close(); clearTimeout(timer); };
  }, [id]);
  return state;
}
