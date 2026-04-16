interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`skeleton-shimmer rounded-lg ${className}`} />
  );
}

export function SkeletonCard({ className = "" }: SkeletonProps) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900 p-4 ${className}`}>
      <Skeleton className="h-3 w-24 mb-3" />
      <Skeleton className="h-5 w-16" />
    </div>
  );
}
