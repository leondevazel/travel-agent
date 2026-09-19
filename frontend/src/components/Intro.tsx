"use client";

import { Airplane, ArrowRight, Compass } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";

const HEADLINE = ["실제", "데이터로", "짜는", "여행", "계획"];

export function Intro({ onStart }: { onStart: () => void }) {
  const reduce = useReducedMotion();

  return (
    <div className="relative flex w-full max-w-3xl flex-col items-center gap-8 text-center">
      {/* A plane crosses the hero once on arrival, then settles. */}
      {!reduce && (
        <motion.div
          className="pointer-events-none absolute -top-10 left-0 text-accent/40"
          initial={{ x: -120, y: 40, rotate: -8, opacity: 0 }}
          animate={{ x: "72vw", y: -30, rotate: 6, opacity: [0, 1, 1, 0] }}
          transition={{ duration: 3.2, ease: "easeInOut", delay: 0.4 }}
        >
          <Airplane size={34} weight="fill" className="rotate-90" />
        </motion.div>
      )}

      <motion.span
        initial={{ opacity: 0, scale: 0.3, rotate: -40 }}
        animate={{ opacity: 1, scale: 1, rotate: 0 }}
        transition={{ type: "spring", stiffness: 240, damping: 14 }}
        className="flex h-16 w-16 animate-wobble items-center justify-center rounded-2xl bg-accent/10 text-accent shadow-lg shadow-accent/10"
      >
        <Compass size={30} weight="fill" />
      </motion.span>

      {/* Word-by-word reveal: each word rises and un-blurs in sequence. */}
      <motion.h1
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.09, delayChildren: 0.15 } } }}
        className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-5xl font-bold tracking-tight text-foreground sm:text-6xl"
      >
        {HEADLINE.map((word) => (
          <motion.span
            key={word}
            variants={{
              hidden: { opacity: 0, y: 40, filter: "blur(8px)" },
              show: {
                opacity: 1,
                y: 0,
                filter: "blur(0px)",
                transition: { type: "spring", stiffness: 180, damping: 18 },
              },
            }}
            className="inline-block"
          >
            {word}
          </motion.span>
        ))}
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.75, type: "spring", stiffness: 200, damping: 24 }}
        className="max-w-md text-balance text-lg text-foreground/60"
      >
        실시간 항공권, 숙소, 날씨를 검색해서 당신의 일정에 딱 맞는 여행 계획을 만들어드려요.
      </motion.p>

      <motion.button
        type="button"
        onClick={onStart}
        initial={{ opacity: 0, y: 16, scale: 0.85 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ delay: 0.9, type: "spring", stiffness: 300, damping: 16 }}
        whileHover={{ scale: 1.06, y: -3 }}
        whileTap={{ scale: 0.93 }}
        className="group relative flex items-center gap-2 overflow-hidden rounded-full bg-accent px-8 py-4 text-base font-semibold text-accent-foreground shadow-xl shadow-accent/30"
      >
        {/* Shine sweep on hover. */}
        <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
        <span className="relative z-10">여행 계획 시작하기</span>
        <ArrowRight
          size={18}
          weight="bold"
          className="relative z-10 transition-transform duration-200 group-hover:translate-x-1"
        />
      </motion.button>
    </div>
  );
}
