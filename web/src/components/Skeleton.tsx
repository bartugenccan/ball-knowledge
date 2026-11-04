export function Skeleton({ className = "h-40" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-busy="true" aria-label="Yükleniyor" />;
}

/** Placeholder shaped like the player page (hero block + attribute columns). */
export function PlayerSkeleton() {
  return (
    <div aria-busy="true" aria-label="Yükleniyor">
      <div className="skeleton h-[420px]" />
      <div className="wrap mt-10 grid gap-10 lg:grid-cols-3">
        <div className="skeleton h-96" />
        <div className="skeleton h-96" />
        <div className="skeleton h-96" />
      </div>
    </div>
  );
}
