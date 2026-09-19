"use client";

import { CaretLeft, CaretRight, MapPin, Pause, Play } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ItineraryDay } from "@/lib/api";
import { fetchLocationImage } from "@/lib/locationImage";

const STOP_DURATION_MS = 5000;

type Stop = { dayIndex: number; day: ItineraryDay; location: string; stopIndex: number };

function flatten(days: ItineraryDay[]): Stop[] {
  return days.flatMap((day, dayIndex) =>
    (day.locations.length ? day.locations : [`Day ${day.day_number}`]).map((location, stopIndex) => ({
      dayIndex,
      day,
      location,
      stopIndex,
    }))
  );
}

export function TripJourney({ days }: { days: ItineraryDay[] }) {
  const reduce = useReducedMotion();
  const stops = useMemo(() => flatten(days), [days]);

  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [playing, setPlaying] = useState(true);
  const [images, setImages] = useState<Record<string, string | null>>({});

  // Reset when a new itinerary arrives, without an effect.
  const [prevStops, setPrevStops] = useState(stops);
  if (stops !== prevStops) {
    setPrevStops(stops);
    setIndex(0);
    setDirection(1);
    setPlaying(true);
  }

  const stop = stops[index];

  const go = useCallback(
    (next: number) => {
      if (!stops.length) return;
      const wrapped = (next + stops.length) % stops.length;
      setDirection(next > index ? 1 : -1);
      setIndex(wrapped);
    },
    [index, stops.length]
  );

  // Prefetch the current stop's photo plus the next one, so advancing
  // doesn't flash an empty frame.
  useEffect(() => {
    const wanted = [stops[index], stops[(index + 1) % stops.length]].filter(Boolean);
    let cancelled = false;
    for (const s of wanted) {
      if (s.location in images) continue;
      fetchLocationImage(s.location).then((url) => {
        if (!cancelled) setImages((prev) => (s.location in prev ? prev : { ...prev, [s.location]: url }));
      });
    }
    return () => {
      cancelled = true;
    };
  }, [index, stops, images]);

  useEffect(() => {
    if (!playing || reduce || stops.length < 2) return;
    const timer = setTimeout(() => go(index + 1), STOP_DURATION_MS);
    return () => clearTimeout(timer);
  }, [playing, reduce, index, stops.length, go]);

  if (!stop) return null;
  const image = images[stop.location];
  const dayStops = stop.day.locations.length ? stop.day.locations : [stop.location];

  return (
    <div className="flex flex-col gap-4">
      <div className="relative h-[68vh] min-h-[420px] w-full overflow-hidden rounded-2xl bg-zinc-900 shadow-2xl">
        <AnimatePresence mode="popLayout" custom={direction} initial={false}>
          <motion.div
            key={`${stop.dayIndex}-${stop.stopIndex}`}
            custom={direction}
            initial={{ opacity: 0, scale: 1.25, filter: "blur(12px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 1.1, filter: "blur(8px)" }}
            transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
            className="absolute inset-0"
          >
            {image ? (
              <motion.img
                src={image}
                alt={stop.location}
                initial={{ scale: 1.02, x: direction > 0 ? 24 : -24 }}
                animate={reduce ? { scale: 1.02, x: 0 } : { scale: 1.22, x: direction > 0 ? -24 : 24 }}
                transition={{ duration: STOP_DURATION_MS / 1000 + 2, ease: "linear" }}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-accent/40 via-sky-500/20 to-zinc-900">
                <motion.div
                  animate={reduce ? {} : { scale: [1, 1.15, 1], opacity: [0.4, 0.7, 0.4] }}
                  transition={{ duration: 1.6, repeat: Infinity }}
                >
                  <MapPin size={44} weight="fill" className="text-white/60" />
                </motion.div>
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-black/40" />
          </motion.div>
        </AnimatePresence>

        {/* Day chip */}
        <motion.div
          key={`chip-${stop.dayIndex}`}
          initial={{ opacity: 0, y: -16, scale: 0.85 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 22 }}
          className="absolute left-5 top-5 rounded-full bg-white/15 px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-white backdrop-blur-md"
        >
          Day {stop.day.day_number} · {stop.day.date}
        </motion.div>

        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause tour" : "Play tour"}
          className="absolute right-5 top-5 flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur-md transition hover:bg-white/25"
        >
          {playing ? <Pause size={15} weight="fill" /> : <Play size={15} weight="fill" />}
        </button>

        {/* Stop title + activities */}
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-3 p-6 pb-20 text-white">
          <AnimatePresence mode="wait">
            <motion.h3
              key={stop.location}
              initial={{ opacity: 0, y: 28, letterSpacing: "0.18em" }}
              animate={{ opacity: 1, y: 0, letterSpacing: "0em" }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-center gap-2 text-3xl font-bold drop-shadow-lg sm:text-4xl"
            >
              <MapPin size={26} weight="fill" className="shrink-0 text-accent" />
              {stop.location}
            </motion.h3>
          </AnimatePresence>

          <motion.ul
            key={`acts-${stop.dayIndex}`}
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07, delayChildren: 0.15 } } }}
            className="flex max-w-xl flex-col gap-1 text-sm text-white/85"
          >
            {stop.day.activities.map((activity, i) => (
              <motion.li
                key={i}
                variants={{
                  hidden: { opacity: 0, x: -18 },
                  show: { opacity: 1, x: 0, transition: { type: "spring", stiffness: 260, damping: 24 } },
                }}
              >
                {activity}
              </motion.li>
            ))}
          </motion.ul>
        </div>

        {/* Thumbnail strip of this day's stops */}
        <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 px-6 py-4">
          {dayStops.map((loc, i) => {
            const active = i === stop.stopIndex;
            return (
              <motion.button
                key={loc}
                type="button"
                onClick={() => go(index - stop.stopIndex + i)}
                aria-label={loc}
                whileHover={{ scale: 1.06, y: -3 }}
                whileTap={{ scale: 0.94 }}
                animate={{ opacity: active ? 1 : 0.55 }}
                className="relative h-10 overflow-hidden rounded-lg border border-white/25 bg-black/40 px-3 text-left text-[11px] font-medium text-white backdrop-blur-md"
              >
                <span className="relative z-10 flex h-full items-center">{loc}</span>
                {active && !reduce && (
                  <motion.span
                    className="absolute inset-y-0 left-0 z-0 bg-accent/70"
                    initial={{ width: "0%" }}
                    animate={{ width: playing ? "100%" : "0%" }}
                    transition={{ duration: STOP_DURATION_MS / 1000, ease: "linear" }}
                  />
                )}
              </motion.button>
            );
          })}
        </div>

        <motion.button
          type="button"
          onClick={() => go(index - 1)}
          aria-label="Previous stop"
          whileHover={{ scale: 1.15, x: -3 }}
          whileTap={{ scale: 0.85 }}
          className="absolute left-4 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-md"
        >
          <CaretLeft size={20} weight="bold" />
        </motion.button>
        <motion.button
          type="button"
          onClick={() => go(index + 1)}
          aria-label="Next stop"
          whileHover={{ scale: 1.15, x: 3 }}
          whileTap={{ scale: 0.85 }}
          className="absolute right-4 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-md"
        >
          <CaretRight size={20} weight="bold" />
        </motion.button>
      </div>

      {/* Whole-trip progress: one segment per stop, grouped by day */}
      <div className="flex items-center gap-1.5">
        {stops.map((s, i) => (
          <motion.button
            key={`${s.dayIndex}-${s.stopIndex}`}
            type="button"
            onClick={() => go(i)}
            aria-label={`Go to ${s.location}`}
            whileHover={{ scaleY: 2.2 }}
            animate={{
              backgroundColor: i === index ? "var(--accent)" : "var(--border)",
              flexGrow: i === index ? 3 : 1,
            }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="h-1.5 rounded-full"
          />
        ))}
      </div>

      {stop.day.notes && (
        <motion.p
          key={`notes-${stop.dayIndex}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-xs text-foreground/55"
        >
          {stop.day.notes}
        </motion.p>
      )}
    </div>
  );
}
