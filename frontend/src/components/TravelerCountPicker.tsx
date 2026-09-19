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
      <motion.button
        type="button"
        onClick={() => onChange(Math.max(1, count - 1))}
        disabled={count <= 1}
        aria-label="Remove a traveler"
        whileHover={count > 1 ? { scale: 1.15 } : undefined}
        whileTap={count > 1 ? { scale: 0.85 } : undefined}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground disabled:opacity-30"
      >
        <Minus size={16} weight="bold" />
      </motion.button>

      <div className="flex min-h-9 min-w-[7rem] flex-wrap items-center gap-1.5">
        <AnimatePresence initial={false}>
          {Array.from({ length: count }, (_, i) => (
            <motion.span
              key={i}
              initial={reduce ? false : { opacity: 0, scale: 0.2, y: -14, rotate: -25 }}
              animate={{ opacity: 1, scale: 1, y: 0, rotate: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.2, y: 14, rotate: 25 }}
              transition={{ type: "spring", stiffness: 500, damping: 18 }}
              whileHover={{ scale: 1.15, y: -3 }}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/10 text-accent"
            >
              <User size={18} weight="fill" />
            </motion.span>
          ))}
        </AnimatePresence>
      </div>

      <motion.button
        type="button"
        onClick={() => onChange(Math.min(MAX_TRAVELERS, count + 1))}
        disabled={count >= MAX_TRAVELERS}
        aria-label="Add a traveler"
        whileHover={count < MAX_TRAVELERS ? { scale: 1.15 } : undefined}
        whileTap={count < MAX_TRAVELERS ? { scale: 0.85 } : undefined}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground disabled:opacity-30"
      >
        <Plus size={16} weight="bold" />
      </motion.button>
    </div>
  );
}
