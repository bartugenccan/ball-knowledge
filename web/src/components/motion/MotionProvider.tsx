"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/**
 * Honour the OS "reduce motion" setting app-wide: transform animations (slides, scale,
 * bar growth) jump to their end state; opacity fades stay. Deciding this in one place
 * keeps server and client markup identical (no hydration mismatch).
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
