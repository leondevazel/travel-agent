"use client";

import { Airplane, Cloud } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";

// Clouds drift via CSS, not Motion, for one reason: CSS honours a NEGATIVE
// animation-delay (start mid-flight), so they're already spread across the
// strip on the first frame instead of all entering from the right together.
const CLOUDS = [
  { top: "10%", size: 34, duration: 9, delay: -1, opacity: 0.3 },
  { top: "60%", size: 22, duration: 6.5, delay: -4, opacity: 0.22 },
  { top: "32%", size: 46, duration: 13, delay: -8, opacity: 0.15 },
  { top: "76%", size: 28, duration: 8, delay: -6, opacity: 0.2 },
];

export function GeneratingTransition({ destination }: { destination: string }) {
  const reduce = useReducedMotion();

  return (
    <div className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-10 text-center">
      <div className="relative h-40 w-full max-w-xl overflow-hidden">
        {/* Parallax cloud layers: different speeds sell the sense of travel. */}
        {CLOUDS.map((cloud, i) => (
          <div
            key={i}
            className="absolute text-foreground"
            style={{
              top: cloud.top,
              opacity: cloud.opacity,
              animation: `drift-cloud ${cloud.duration}s linear ${cloud.delay}s infinite`,
            }}
          >
            <Cloud size={cloud.size} weight="fill" />
          </div>
        ))}

        <div className="absolute top-1/2 h-px w-full -translate-y-1/2 border-t border-dashed border-border" />

        <motion.div
          className="absolute top-1/2 text-accent drop-shadow-lg"
          initial={{ x: -48, y: "-50%" }}
          animate={reduce ? { x: 560 } : { x: 560, y: ["-50%", "-72%", "-50%", "-32%", "-50%"] }}
          transition={
            reduce
              ? { duration: 0.01 }
              : {
                  x: { duration: 3.4, repeat: Infinity, ease: "easeInOut" },
                  y: { duration: 2.1, repeat: Infinity, ease: "easeInOut" },
                }
          }
        >
          <Airplane size={38} weight="fill" className="rotate-90" />
        </motion.div>
      </div>

      <div className="flex flex-col items-center gap-3">
        <motion.p
          className="text-xl font-semibold text-foreground"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 220, damping: 20 }}
        >
          {destination ? `${destination}(으)로 떠나는 중...` : "떠나는 중..."}
        </motion.p>
        <p className="max-w-sm text-balance text-sm text-foreground/60">
          실시간으로 항공편, 숙소, 일정을 찾고 있어요. 조금만 기다려주세요.
        </p>
        <div className="mt-2 flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-accent"
              animate={reduce ? {} : { opacity: [0.25, 1, 0.25], scale: [1, 1.4, 1] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.18 }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
