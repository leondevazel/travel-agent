"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { TagListInput } from "./TagListInput";
import { TravelerCountPicker } from "./TravelerCountPicker";

const FIELD = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 220, damping: 24 } },
} as const;

export type TripFormValues = {
  travelers: number;
  origin: string;
  destinations: string[];
  mustVisit: string[];
  startDate: string;
  endDate: string;
  budgetUsd: string;
  interests: string[];
  pace: "relaxed" | "balanced" | "packed";
};

const PACE_OPTIONS: TripFormValues["pace"][] = ["relaxed", "balanced", "packed"];

export function tripFormToMessage(v: TripFormValues): string {
  const cities = v.destinations.join(" then ");
  const parts = [
    `Plan a trip for ${v.travelers} traveler${v.travelers > 1 ? "s" : ""} from ${v.origin} to ${cities}`,
    `departing ${v.startDate} and returning ${v.endDate}`,
    v.budgetUsd ? `budget $${v.budgetUsd}` : null,
    v.interests.length ? `interested in ${v.interests.join(", ")}` : null,
    v.mustVisit.length ? `must visit: ${v.mustVisit.join(", ")}` : null,
    `pace: ${v.pace}`,
  ].filter(Boolean);
  return parts.join(", ") + ".";
}

export function TripForm({
  onSubmit,
}: {
  onSubmit: (message: string, values: TripFormValues) => void;
}) {
  const [travelers, setTravelers] = useState(1);
  const [origin, setOrigin] = useState("");
  const [destinations, setDestinations] = useState<string[]>([]);
  const [mustVisit, setMustVisit] = useState<string[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [budgetUsd, setBudgetUsd] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [pace, setPace] = useState<TripFormValues["pace"]>("balanced");

  const canSubmit = origin.trim() && destinations.length > 0 && startDate && endDate;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const values: TripFormValues = {
      travelers,
      origin,
      destinations,
      mustVisit,
      startDate,
      endDate,
      budgetUsd,
      interests,
      pace,
    };
    onSubmit(tripFormToMessage(values), values);
  }

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
      className="flex w-full max-w-lg flex-col gap-6"
    >
      <motion.div variants={FIELD} className="flex flex-col gap-2">
        <span className="text-sm font-medium text-foreground">Travelers</span>
        <TravelerCountPicker count={travelers} onChange={setTravelers} />
      </motion.div>

      <motion.div variants={FIELD} className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="origin" className="text-sm font-medium text-foreground">
            From
          </label>
          <input
            id="origin"
            type="text"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            placeholder="Seoul"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-foreground/40 focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor="pace" className="text-sm font-medium text-foreground">
            Pace
          </label>
          <select
            id="pace"
            value={pace}
            onChange={(e) => setPace(e.target.value as TripFormValues["pace"])}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
          >
            {PACE_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </motion.div>

      <motion.div variants={FIELD}>
        <TagListInput
          label="Destinations (in visit order)"
          placeholder="Type a city and press Enter"
          values={destinations}
          onChange={setDestinations}
        />
      </motion.div>

      <motion.div variants={FIELD} className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="start" className="text-sm font-medium text-foreground">
            Departing
          </label>
          <input
            id="start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor="end" className="text-sm font-medium text-foreground">
            Returning
          </label>
          <input
            id="end"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
          />
        </div>
      </motion.div>

      <motion.div variants={FIELD} className="flex flex-col gap-2">
        <label htmlFor="budget" className="text-sm font-medium text-foreground">
          Budget (USD, optional)
        </label>
        <input
          id="budget"
          type="number"
          min={0}
          value={budgetUsd}
          onChange={(e) => setBudgetUsd(e.target.value)}
          placeholder="2000"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-foreground/40 focus:border-accent focus:outline-none"
        />
      </motion.div>

      <motion.div variants={FIELD}>
        <TagListInput
          label="Interests (optional)"
          placeholder="art, food, hiking..."
          values={interests}
          onChange={setInterests}
        />
      </motion.div>

      <motion.div variants={FIELD}>
        <TagListInput
          label="Must-visit places (optional)"
          placeholder="Eiffel Tower..."
          values={mustVisit}
          onChange={setMustVisit}
        />
      </motion.div>

      <motion.button
        type="submit"
        disabled={!canSubmit}
        variants={FIELD}
        whileHover={canSubmit ? { scale: 1.02, y: -2 } : undefined}
        whileTap={canSubmit ? { scale: 0.97 } : undefined}
        className="mt-2 w-full rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-accent-foreground shadow-lg shadow-accent/20 disabled:opacity-40 disabled:shadow-none"
      >
        Plan my trip
      </motion.button>
    </motion.form>
  );
}
