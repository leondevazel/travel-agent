"use client";

import { Compass } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { useState } from "react";
import { GeneratingTransition } from "@/components/GeneratingTransition";
import { TripForm } from "@/components/TripForm";
import { TripResults } from "@/components/TripResults";
import { createSession, sendMessage, type TurnResponse } from "@/lib/api";

type Step = "intro" | "form" | "generating" | "results";

export default function Home() {
  const [step, setStep] = useState<Step>("intro");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingDestination, setPendingDestination] = useState("");
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
      {step === "intro" && (
        <motion.div
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.12, delayChildren: 0.1 } } }}
          className="flex max-w-md flex-col items-center gap-6 text-center"
        >
          <motion.span
            variants={{ hidden: { opacity: 0, scale: 0.4, rotate: -20 }, show: { opacity: 1, scale: 1, rotate: 0 } }}
            transition={{ type: "spring", stiffness: 260, damping: 16 }}
            className="flex h-14 w-14 animate-wobble items-center justify-center rounded-full bg-accent/10 text-accent"
          >
            <Compass size={26} weight="fill" />
          </motion.span>
          <motion.h1
            variants={{ hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0 } }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            className="text-4xl font-semibold tracking-tight text-balance text-foreground"
          >
            실제 데이터로 짜는 여행 계획
          </motion.h1>
          <motion.p
            variants={{ hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0 } }}
            transition={{ type: "spring", stiffness: 200, damping: 22 }}
            className="text-base text-foreground/60"
          >
            실시간 항공권, 숙소, 날씨를 검색해서 당신의 일정에 딱 맞는 여행 계획을 만들어드려요.
          </motion.p>
          <motion.button
            type="button"
            onClick={() => setStep("form")}
            variants={{ hidden: { opacity: 0, y: 12, scale: 0.9 }, show: { opacity: 1, y: 0, scale: 1 } }}
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            whileHover={{ scale: 1.05, y: -2 }}
            whileTap={{ scale: 0.94 }}
            className="rounded-lg bg-accent px-6 py-3 text-sm font-semibold text-accent-foreground shadow-lg shadow-accent/20"
          >
            여행 계획 시작하기
          </motion.button>
        </motion.div>
      )}

      {step === "form" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full max-w-lg">
          {error && <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
          <TripForm
            onSubmit={(message) => {
              setPendingDestination(message);
              void handleFormSubmit(message);
            }}
          />
        </motion.div>
      )}

      {step === "generating" && <GeneratingTransition destination={extractDestination(pendingDestination)} />}

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

function extractDestination(message: string): string {
  const match = message.match(/to ([^,]+)/);
  return match ? match[1].trim() : "";
}
