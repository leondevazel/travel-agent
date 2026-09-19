// Free, keyless: Wikipedia's search API finds the best-matching page for an
// arbitrary place name and returns its lead image. No account, no cost, no
// pre-authored asset per location.
const WIKI_API = "https://en.wikipedia.org/w/api.php";

type WikiPage = { original?: { source?: string } };

export async function fetchLocationImage(location: string): Promise<string | null> {
  const url = new URL(WIKI_API);
  url.search = new URLSearchParams({
    action: "query",
    generator: "search",
    gsrsearch: location,
    gsrlimit: "1",
    prop: "pageimages",
    piprop: "original",
    format: "json",
    origin: "*",
  }).toString();

  try {
    const res = await fetch(url.toString());
    if (!res.ok) return null;
    const data = await res.json();
    const pages = data?.query?.pages as Record<string, WikiPage> | undefined;
    if (!pages) return null;
    const page = Object.values(pages)[0];
    return page?.original?.source ?? null;
  } catch {
    return null;
  }
}
