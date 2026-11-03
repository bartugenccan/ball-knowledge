export function Skeleton({ className = "h-40" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-busy="true" aria-label="Yükleniyor" />;
}

/** Placeholder shaped like the player page (hero + attribute columns). */
export function PlayerSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Yükleniyor">
      <div className="skeleton h-64" />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="skeleton h-96" />
        <div className="skeleton h-96" />
        <div className="skeleton h-96" />
      </div>
    </div>
  );
}
