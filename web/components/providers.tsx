"use client";
import { LayoutGroup, MotionConfig } from "motion/react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ReaderPreferences } from "./reader-settings";
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ReaderPreferences><MotionConfig reducedMotion="user">
      <TooltipProvider>
        <LayoutGroup>{children}</LayoutGroup>
        <Toaster theme="light" />
      </TooltipProvider>
    </MotionConfig></ReaderPreferences>
  );
}
