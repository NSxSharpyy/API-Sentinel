
export default function EndpointTableSkeleton({
  rows = 4,
}) {
  return (
    <div
      className="animate-pulse space-y-4 p-5"
      role="status"
      aria-label="Loading transactions"
    >
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="grid grid-cols-4 items-center gap-4"
        >
          <div className="h-6 w-16 rounded bg-slate-200" />

          <div className="h-5 w-full rounded bg-slate-200" />

          <div className="h-6 w-14 rounded bg-slate-200" />

          <div className="h-5 w-20 rounded bg-slate-200" />
        </div>
      ))}

      <span className="sr-only">
        Loading API transactions...
      </span>
    </div>
  );
}
