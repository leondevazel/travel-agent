"use client";

import { CaretLeft, CaretRight, MapPin } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import type { ItineraryDay } from "@/lib/api";
import { fetchLocationImage } from "@/lib/locationImage";

export function TripJourney({ days }: { days: ItineraryDay[] }) {
  const [index, setIndex] = useState(0);
  const [images, setImages] = useState<Record<string, string | null>>({});
  // Reset to day 1 whenever a new itinerary arrives (e.g. after a chat
  // refinement), without an effect: https://react.dev/learn/you-might-not-need-an-effect
  const [prevDays, setPrevDays] = useState(days);
  if (days !== prevDays) {
    setPrevDays(days);
    setIndex(0);
    setImages({});
  }
  const day = days[index];

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
        <AnimatePresence mode="wait">
          <motion.div
            key={day.day_number}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6 }}
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

        <button
          type="button"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
          aria-label="Previous day"
          className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur transition active:scale-90 disabled:opacity-0"
        >
          <CaretLeft size={18} weight="bold" />
        </button>
        <button
          type="button"
          onClick={() => setIndex((i) => Math.min(days.length - 1, i + 1))}
          disabled={index === days.length - 1}
          aria-label="Next day"
          className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur transition active:scale-90 disabled:opacity-0"
        >
          <CaretRight size={18} weight="bold" />
        </button>
      </div>

      <div className="flex items-center justify-center gap-2">
        {days.map((d, i) => (
          <button
            key={d.day_number}
            type="button"
            onClick={() => setIndex(i)}
            aria-label={`Go to day ${d.day_number}`}
            className={`h-1.5 rounded-full transition-all ${
              i === index ? "w-6 bg-accent" : "w-1.5 bg-border"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
