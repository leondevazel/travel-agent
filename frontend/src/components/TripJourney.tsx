"use client";

import { CaretLeft, CaretRight, MapPin } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import type { ItineraryDay } from "@/lib/api";
import { fetchLocationImage } from "@/lib/locationImage";

// Days slide in from the side you're travelling toward, so moving forward
// through the trip feels like moving forward through space.
const SLIDE = {
  enter: (direction: number) => ({ opacity: 0, scale: 1.08, x: direction > 0 ? 60 : -60 }),
  center: { opacity: 1, scale: 1, x: 0 },
  exit: (direction: number) => ({ opacity: 0, scale: 0.96, x: direction > 0 ? -60 : 60 }),
};

export function TripJourney({ days }: { days: ItineraryDay[] }) {
  const [index, setIndex] = useState(0);
  // +1 when moving forward through the trip, -1 when going back, so days
  // slide in from the side you're travelling toward.
  const [direction, setDirection] = useState(1);
  const [images, setImages] = useState<Record<string, string | null>>({});
  // Reset to day 1 whenever a new itinerary arrives (e.g. after a chat
  // refinement), without an effect: https://react.dev/learn/you-might-not-need-an-effect
  const [prevDays, setPrevDays] = useState(days);
  if (days !== prevDays) {
    setPrevDays(days);
    setIndex(0);
    setDirection(1);
    setImages({});
  }
  const day = days[index];

  function goTo(next: number) {
    setDirection(next > index ? 1 : -1);
    setIndex(next);
  }

  useEffect(() => {
    if (!day || day.location in images) return;
    let cancelled = false;
    fetchLocationImage(day.location).then((url) => {
      if (!cancelled) setImages((prev) => ({ ...prev, [day.location]: url }));
    });
    return () => {
      cancelled = true;
    };
  }, [day, images]);

  if (!day) return null;
  const image = images[day.location];

  return (
    <div className="flex flex-col gap-4">
      <div className="relative h-[60vh] w-full overflow-hidden rounded-xl bg-zinc-900">
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={day.day_number}
            custom={direction}
            variants={SLIDE}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ type: "spring", stiffness: 180, damping: 26 }}
            className="absolute inset-0"
          >
            {image ? (
              <motion.img
                src={image}
                alt={day.location}
                initial={{ scale: 1 }}
                animate={{ scale: 1.12 }}
                transition={{ duration: 8, ease: "linear" }}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-accent/30 to-zinc-800">
                <MapPin size={40} weight="fill" className="text-white/40" />
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-black/30" />
          </motion.div>
        </AnimatePresence>

        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-2 p-6 text-white">
          <span className="text-xs font-medium uppercase tracking-wide text-white/70">
            Day {day.day_number} · {day.date}
          </span>
          <h3 className="flex items-center gap-1.5 text-2xl font-semibold">
            <MapPin size={20} weight="fill" />
            {day.location}
          </h3>
          <ul className="mt-1 flex flex-col gap-1 text-sm text-white/85">
            {day.activities.map((activity, i) => (
              <li key={i}>{activity}</li>
            ))}
          </ul>
          {day.notes && <p className="mt-1 text-xs text-white/60">{day.notes}</p>}
        </div>

        <motion.button
          type="button"
          onClick={() => goTo(Math.max(0, index - 1))}
          disabled={index === 0}
          aria-label="Previous day"
          whileHover={{ scale: 1.12, x: -2 }}
          whileTap={{ scale: 0.88 }}
          className="absolute left-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur disabled:opacity-0"
        >
          <CaretLeft size={18} weight="bold" />
        </motion.button>
        <motion.button
          type="button"
          onClick={() => goTo(Math.min(days.length - 1, index + 1))}
          disabled={index === days.length - 1}
          aria-label="Next day"
          whileHover={{ scale: 1.12, x: 2 }}
          whileTap={{ scale: 0.88 }}
          className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur disabled:opacity-0"
        >
          <CaretRight size={18} weight="bold" />
        </motion.button>
      </div>

      <div className="flex items-center justify-center gap-2">
        {days.map((d, i) => (
          <motion.button
            key={d.day_number}
            type="button"
            onClick={() => goTo(i)}
            aria-label={`Go to day ${d.day_number}`}
            whileHover={{ scale: 1.4 }}
            whileTap={{ scale: 0.8 }}
            animate={{ width: i === index ? 24 : 6 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
            className={`h-1.5 rounded-full ${i === index ? "bg-accent" : "bg-border"}`}
          />
        ))}
      </div>
    </div>
  );
}
