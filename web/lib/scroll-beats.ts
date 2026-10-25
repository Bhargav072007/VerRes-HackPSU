// Five 60vh beats: animate for 42vh, hold for 18vh. Pure mapping makes reversal exact.
export function scrollBeats(progress: number): number[] {
  const p = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
  return Array.from({ length: 5 }, (_, i) => Math.max(0, Math.min(1, (p * 5 - i) / .7)));
}
