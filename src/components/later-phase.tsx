export function LaterPhase({ title }: { title: string }) {
  return (
    <section>
      <h2 className="font-serif text-3xl text-ink">{title}</h2>
      <p className="mt-3 max-w-prose text-muted">This section is part of a later phase.</p>
    </section>
  );
}
