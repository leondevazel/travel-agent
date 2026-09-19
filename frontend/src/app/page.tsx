"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { GeneratingTransition } from "@/components/GeneratingTransition";
import { Intro } from "@/components/Intro";
import { TripForm } from "@/components/TripForm";
import { TripResults } from "@/components/TripResults";
import { createSession, sendMessage, type TurnResponse } from "@/lib/api";

type Step = "intro" | "form" | "generating" | "results";

export default function Home() {
  const [step, setStep] = useState<Step>("intro");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingDestinations, setPendingDestinations] = useState<string[]>([]);
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [isRefining, setIsRefining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFormSubmit(message: string) {
    setError(null);
    setStep("generating");
    try {
      const { session_id } = await createSession();
      setSessionId(session_id);
      const turn = await sendMessage(session_id, message);
      setResult(turn);
      setStep("results");
    } catch {
      setError("여행 계획을 만드는 중 문제가 생겼어요. 다시 시도해주세요.");
      setStep("form");
    }
  }

  async function handleRefine(message: string) {
    if (!sessionId) return;
    setIsRefining(true);
    setError(null);
    try {
      const turn = await sendMessage(sessionId, message);
      setResult(turn);
    } catch {
      setError("수정 요청을 처리하지 못했어요. 다시 시도해주세요.");
    } finally {
      setIsRefining(false);
    }
  }

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-16">
      {step === "intro" && <Intro onStart={() => setStep("form")} />}

      {step === "form" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full max-w-lg">
          {error && <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
          <TripForm
            onSubmit={(message, values) => {
              setPendingDestinations(values.destinations);
              void handleFormSubmit(message);
            }}
          />
        </motion.div>
      )}

      {step === "generating" && <GeneratingTransition destinations={pendingDestinations} />}

      {step === "results" && result && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full">
          {error && <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
          <TripResults
            brief={result.trip_brief}
            flights={result.flight_candidates}
            hotels={result.hotel_candidates}
            itinerary={result.itinerary}
            warnings={result.warnings}
            reply={result.reply}
            onRefine={handleRefine}
            isRefining={isRefining}
          />
        </motion.div>
      )}
    </main>
  );
}
