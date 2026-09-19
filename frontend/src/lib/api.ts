const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type TripBrief = {
  destination: string | null;
  origin: string | null;
  additional_destinations: string[];
  must_visit: string[];
  start_date: string | null;
  end_date: string | null;
  budget_usd: number | null;
  interests: string[];
  pace: "relaxed" | "balanced" | "packed" | null;
};

export type FlightCandidate = {
  carrier: string;
  price_usd: number;
  departure_time: string;
  arrival_time: string;
  origin: string;
  destination: string;
  stops: number;
};

export type HotelCandidate = {
  name: string;
  price_usd_per_night: number;
  rating: number | null;
  address: string;
};

export type ItineraryDay = {
  day_number: number;
  date: string;
  activities: string[];
  notes: string;
};

export type TurnResponse = {
  reply: string;
  trip_brief: TripBrief;
  flight_candidates: FlightCandidate[];
  hotel_candidates: HotelCandidate[];
  itinerary: ItineraryDay[];
  warnings: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  return res.json();
}

export function createSession(): Promise<{ session_id: string }> {
  return request("/sessions", { method: "POST" });
}

export function sendMessage(sessionId: string, content: string): Promise<TurnResponse> {
  return request(`/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}
