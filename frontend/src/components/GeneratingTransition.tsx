"use client";

import { Airplane } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";

export function GeneratingTransition({ destination }: { destination: string }) {
  const reduce = useReducedMotion();

  return (
    <div className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-8 text-center">
      <div className="relative h-16 w-64 overflow-hidden">
        <div className="absolute top-1/2 h-px w-full -translate-y-1/2 border-t border-dashed border-border" />
        <motion.div
          className="absolute top-1/2 -translate-y-1/2 text-accent"
          initial={{ x: -32 }}
          animate={reduce ? { x: 240 } : { x: 240, y: [0, -6, 0] }}
          transition={
            reduce
              ? { duration: 0.01 }
              : { x: { duration: 2.2, repeat: Infinity, ease: "linear" }, y: { duration: 1.1, repeat: Infinity, ease: "easeInOut" } }
          }
        >
          <Airplane size={32} weight="fill" className="rotate-90" />
        </motion.div>
      </div>
      <p className="text-lg font-medium text-foreground">
        {destination ? `${destination}(으)로 떠나는 중...` : "떠나는 중..."}
      </p>
      <p className="max-w-sm text-balance text-sm text-foreground/60">
        실시간으로 항공편, 숙소, 일정을 찾고 있어요. 조금만 기다려주세요.
      </p>
    </div>
  );
}
