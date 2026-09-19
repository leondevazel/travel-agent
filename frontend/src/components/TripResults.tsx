"use client";

import { Airplane, Bed, PaperPlaneRight, Warning } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { useState } from "react";
import type { FlightCandidate, HotelCandidate, ItineraryDay, TripBrief } from "@/lib/api";

export function TripResults({
  brief,
  flights,
  hotels,
  itinerary,
  warnings,
  reply,
  onRefine,
  isRefining,
}: {
  brief: TripBrief;
  flights: FlightCandidate[];
  hotels: HotelCandidate[];
  itinerary: ItineraryDay[];
  warnings: string[];
  reply: string;
  onRefine: (message: string) => void;
  isRefining: boolean;
}) {
  const [draft, setDraft] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const message = draft.trim();
    if (!message || isRefining) return;
    onRefine(message);
    setDraft("");
  }

  const route = [brief.destination, ...brief.additional_destinations].filter(Boolean).join(" -> ");
  // The backend's reply is chat-formatted (intro line + day-by-day + notes),
  // but the day-by-day and notes are already rendered as structured sections
  // below. Only the intro line adds anything new here.
  const replyIntro = reply.split("\n")[0];

  return (
    <div className="flex w-full max-w-2xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{route || "Your trip"}</h1>
        {replyIntro && <p className="mt-2 text-sm text-foreground/70">{replyIntro}</p>}
      </div>

      {warnings.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          {warnings.map((w) => (
            <div key={w} className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
              <Warning size={16} weight="fill" className="mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {itinerary.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-foreground/60">Itinerary</h2>
          {itinerary.map((day, i) => (
            <motion.div
              key={day.day_number}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="rounded-lg border border-border bg-surface p-4"
            >
              <div className="flex items-baseline justify-between">
                <span className="font-medium text-foreground">Day {day.day_number}</span>
                <span className="text-xs text-foreground/50">{day.date}</span>
              </div>
              <ul className="mt-2 flex flex-col gap-1 text-sm text-foreground/80">
                {day.activities.map((activity, j) => (
                  <li key={j}>{activity}</li>
                ))}
              </ul>
              {day.notes && <p className="mt-2 text-xs text-foreground/50">{day.notes}</p>}
            </motion.div>
          ))}
        </section>
      )}

      {flights.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-medium text-foreground/60">
            <Airplane size={16} /> Flights
          </h2>
          <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
            {flights.map((f, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 text-sm">
                <span className="text-foreground">
                  {f.carrier} · {f.origin} to {f.destination}
                </span>
                <span className="font-medium text-foreground">${f.price_usd}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {hotels.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-medium text-foreground/60">
            <Bed size={16} /> Hotels
          </h2>
          <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
            {hotels.map((h, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 text-sm">
                <span className="text-foreground">
                  {h.name} · {h.address}
                </span>
                <span className="font-medium text-foreground">${h.price_usd_per_night}/night</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <form onSubmit={submit} className="flex items-center gap-2 border-t border-border pt-4">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="예: 2일차 느슨하게 바꿔줘"
          disabled={isRefining}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-foreground/40 focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isRefining || !draft.trim()}
          aria-label="Send"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground transition active:scale-95 disabled:opacity-40"
        >
          <PaperPlaneRight size={16} weight="fill" />
        </button>
      </form>
    </div>
  );
}
