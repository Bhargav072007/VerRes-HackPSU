export const motionTokens = {
  spring: { type: "spring", stiffness: 380, damping: 32 },
  soft: { type: "spring", stiffness: 200, damping: 28 },
  fade: { duration: 0.22 },
  stagger: 0.035,
  reviewStagger: 0.06,
  layout: { duration: 0.36, ease: [.2, .7, .2, 1] },
} as const;

export const counterTiming = { duration: 360, easing: "cubic-bezier(.2,.7,.2,1)" };
