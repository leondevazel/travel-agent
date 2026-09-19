export function AnimatedBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      <div className="absolute -left-32 -top-32 h-96 w-96 animate-blob-a rounded-full bg-accent/25 blur-3xl" />
      <div className="absolute -right-24 top-1/3 h-80 w-80 animate-blob-b rounded-full bg-sky-400/20 blur-3xl" />
      <div className="absolute bottom-[-6rem] left-1/4 h-96 w-96 animate-blob-c rounded-full bg-accent/15 blur-3xl" />
    </div>
  );
}
