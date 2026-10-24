"use client";
import { use } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowLeft, FileCheck2 } from "lucide-react";
import { motionTokens } from "@/lib/motion";
export default function CheckPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const reduced = useReducedMotion();
  return (
    <main id="main" className="mx-auto min-h-[70vh] max-w-2xl px-6 py-20">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm text-muted-foreground"
      >
        <ArrowLeft size={16} /> Back to VerRes
      </Link>
      <motion.section
        layoutId="job"
        transition={reduced ? { duration: 0 } : motionTokens.layout}
        className="rounded-xl border bg-white p-8"
      >
        <FileCheck2 size={28} strokeWidth={1.4} />
        <h1 className="mt-5 font-serif text-3xl">Your paper is in.</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Submission received. The live review view is coming in the next
          update.
        </p>
        <p className="mt-6 break-all text-xs text-muted-foreground">
          Review ID: {id}
        </p>
      </motion.section>
    </main>
  );
}
