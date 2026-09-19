"use client";

import { Airplane, Cloud, MapPin } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";

const LEG_SECONDS = 2.6;

// Clouds drift via CSS, not Motion, for one reason: CSS honours a NEGATIVE
// animation-delay (start mid-flight), so they're already spread across the
// sky on the first frame instead of all entering from the right together.
const CLOUDS = [
  { top: "8%", size: 30, duration: 11, delay: -2, opacity: 0.28 },
  { top: "68%", size: 20, duration: 7.5, delay: -5, opacity: 0.2 },
  { top: "28%", size: 44, duration: 15, delay: -9, opacity: 0.13 },
  { top: "82%", size: 26, duration: 9, delay: -7, opacity: 0.18 },
];

/** "피렌체" -> "피렌체로", "서울" -> "서울로", "런던" -> "런던으로". */
function withDirectionParticle(place: string): string {
  const last = place.trim().slice(-1);
  const code = last.charCodeAt(0);
  const isHangulSyllable = code >= 0xac00 && code <= 0xd7a3;
  if (!isHangulSyllable) return `${place}로`;
  const finalConsonant = (code - 0xac00) % 28;
  // No final consonant, or a ㄹ final, takes 로; everything else takes 으로.
  return finalConsonant === 0 || finalConsonant === 8 ? `${place}로` : `${place}으로`;
}

function routeLabel(destinations: string[]): string {
  if (!destinations.length) return "떠나는 중...";
  const head = destinations.slice(0, -1);
  const tail = withDirectionParticle(destinations[destinations.length - 1]);
  return `${[...head, tail].join(", ")} 떠나는 중...`;
}

export function GeneratingTransition({ destinations }: { destinations: string[] }) {
  const reduce = useReducedMotion();
  const stops = destinations.length ? destinations : ["여행지"];
  // The plane flies origin -> stop -> stop..., so there's one more point on
  // the line than there are destinations.
  const points = ["출발", ...stops];
  const totalSeconds = LEG_SECONDS * (points.length - 1);

  return (
    <div className="flex min-h-[60vh] w-full max-w-2xl flex-col items-center justify-center gap-12">
      <div className="relative h-44 w-full overflow-hidden">
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

        {/* The route: a dashed line with a pin per stop. */}
        <div className="absolute inset-x-6 top-1/2 h-px -translate-y-1/2 border-t border-dashed border-foreground/25" />

        <div className="absolute inset-x-6 top-1/2 flex -translate-y-1/2 items-center justify-between">
          {points.map((point, i) => {
            const arrivalAt = LEG_SECONDS * i;
            return (
              <div key={`${point}-${i}`} className="relative flex flex-col items-center">
                <motion.span
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-foreground/20 bg-background text-foreground/40"
                  animate={
                    reduce
                      ? {}
                      : {
                          scale: [1, 1, 1.45, 1.1, 1.1],
                          color: [
                            "var(--color-foreground)",
                            "var(--color-foreground)",
                            "var(--color-accent)",
                            "var(--color-accent)",
                            "var(--color-accent)",
                          ],
                          borderColor: [
                            "color-mix(in srgb, var(--foreground) 20%, transparent)",
                            "color-mix(in srgb, var(--foreground) 20%, transparent)",
                            "var(--accent)",
                            "var(--accent)",
                            "var(--accent)",
                          ],
                        }
                  }
                  transition={{
                    duration: totalSeconds,
                    times: [0, arrivalAt / totalSeconds, Math.min((arrivalAt + 0.35) / totalSeconds, 1), Math.min((arrivalAt + 0.8) / totalSeconds, 1), 1],
                    repeat: Infinity,
                    repeatDelay: 0.6,
                  }}
                >
                  <MapPin size={14} weight="fill" />
                </motion.span>
                <span className="absolute top-9 whitespace-nowrap text-[11px] font-medium text-foreground/50">
                  {i === 0 ? "" : point}
                </span>
              </div>
            );
          })}
        </div>

        {/* The plane hops from pin to pin, banking as it goes. The track is
            padded by half a pin so 0%..100% lands exactly on pin centres,
            and the mover is w-full so a percentage x means "percent of the
            track", not "percent of the plane". */}
        <div className="pointer-events-none absolute inset-x-6 top-1/2 z-10 -translate-y-1/2 px-[14px]">
          <motion.div
            className="w-full"
            initial={{ x: "0%" }}
            animate={
              reduce
                ? { x: "100%" }
                : {
                    x: points.map((_, i) => `${(i / (points.length - 1)) * 100}%`),
                    y: points.map((_, i) => (i === 0 || i === points.length - 1 ? 0 : -14)),
                    rotate: points.map((_, i) => (i === 0 || i === points.length - 1 ? 0 : -8)),
                  }
            }
            transition={{
              duration: totalSeconds,
              times: points.map((_, i) => i / (points.length - 1)),
              ease: "easeInOut",
              repeat: Infinity,
              repeatDelay: 0.6,
            }}
          >
            <Airplane
              size={30}
              weight="fill"
              className="-translate-x-1/2 -translate-y-1/2 rotate-90 text-accent drop-shadow-lg"
            />
          </motion.div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-3 text-center">
        <motion.p
          className="text-2xl font-bold text-balance text-foreground"
          initial={{ opacity: 0, y: 12, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ type: "spring", stiffness: 200, damping: 22 }}
        >
          {routeLabel(stops)}
        </motion.p>
        <p className="max-w-sm text-balance text-sm text-foreground/60">
          실시간으로 항공편, 숙소, 일정을 찾고 있어요. 조금만 기다려주세요.
        </p>
        <div className="mt-2 flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-accent"
              animate={reduce ? {} : { opacity: [0.25, 1, 0.25], scale: [1, 1.5, 1] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.18 }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
