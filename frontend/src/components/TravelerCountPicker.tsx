"use client";

import { Minus, Plus, User } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

const MAX_TRAVELERS = 8;

export function TravelerCountPicker({
  count,
  onChange,
}: {
  count: number;
  onChange: (next: number) => void;
}) {
  const reduce = useReducedMotion();

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={() => onChange(Math.max(1, count - 1))}
        disabled={count <= 1}
        aria-label="Remove a traveler"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground transition active:scale-95 disabled:opacity-30"
      >
        <Minus size={16} weight="bold" />
      </button>

      <div className="flex min-h-9 min-w-[7rem] flex-wrap items-center gap-1.5">
        <AnimatePresence initial={false}>
          {Array.from({ length: count }, (_, i) => (
            <motion.span
              key={i}
              initial={reduce ? false : { opacity: 0, scale: 0.4, y: 6 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.4, y: 6 }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/10 text-accent"
            >
              <User size={18} weight="fill" />
            </motion.span>
          ))}
        </AnimatePresence>
      </div>

      <button
        type="button"
        onClick={() => onChange(Math.min(MAX_TRAVELERS, count + 1))}
        disabled={count >= MAX_TRAVELERS}
        aria-label="Add a traveler"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground transition active:scale-95 disabled:opacity-30"
      >
        <Plus size={16} weight="bold" />
      </button>
    </div>
  );
}
