export const motionTokens = {
  spring: { type: "spring", stiffness: 380, damping: 32 },
  soft: { type: "spring", stiffness: 200, damping: 28 },
  fade: { duration: 0.18 },
  stagger: 0.035,
  reviewStagger: 0.06,
  layout: { duration: 0.35, ease: "easeInOut" },
} as const;

export const counterTiming = { duration: 350, easing: "ease-out" };
