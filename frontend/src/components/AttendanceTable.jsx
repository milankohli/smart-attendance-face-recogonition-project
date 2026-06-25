import { useEffect, useRef } from "react";

// ── Status badge ───────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    present: "bg-emerald-500/15 text-emerald-400",
    late:    "bg-amber-500/15 text-amber-400",
    absent:  "bg-slate-700 text-slate-400",
  };
  const cls = map[status?.toLowerCase()] ?? "bg-slate-700 text-slate-400";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${cls}`}>
      {status ?? "—"}
    </span>
  );
}

// ── Confidence band badge ──────────────────────────────────────────────────
function ConfidenceBadge({ band }) {
  const map = {
    high: "bg-emerald-500/15 text-emerald-400",
    medium: "bg-amber-500/15 text-amber-400",
    low: "bg-rose-500/15 text-rose-400",
  };
  const cls = map[band?.toLowerCase()] ?? "bg-slate-700 text-slate-400";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {band ?? "—"}
    </span>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────
function SkeletonRows({ count = 7 }) {
  return Array.from({ length: count }).map((_, i) => (
    <tr key={i}>
      {[36, 20, 16, 12, 12, 14, 10].map((w, j) => (
        <td key={j} className="px-6 py-3.5">
          <div className={`h-4 w-${w} animate-pulse rounded bg-slate-800`} />
        </td>
      ))}
    </tr>
  ));
}

const COLUMNS = ["Student", "Code", "Date", "Time", "Status", "Confidence", "Similarity"];

/**
 * AttendanceTable
 *
 * Props:
 *   records      AttendanceReadWithStudent[]
 *   loading      bool
 *   liveMode     bool    When true, new rows are highlighted and auto-scrolled into view
 *   page         number
 *   pageSize     number
 *   total        number
 *   onPage       (page) => void
 *   onDelete     (record) => void   optional — shown only when provided
 */
export default function AttendanceTable({
  records = [],
  loading = false,
  liveMode = false,
  page = 1,
  pageSize = 50,
  total = 0,
  onPage,
  onDelete,
}) {
  const tbodyRef = useRef(null);
  const prevLengthRef = useRef(records.length);

  // Auto-scroll to the newest row when in live mode
  useEffect(() => {
    if (!liveMode) return;
    if (records.length > prevLengthRef.current && tbodyRef.current) {
      const rows = tbodyRef.current.querySelectorAll("tr[data-live]");
      if (rows.length) rows[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    prevLengthRef.current = records.length;
  }, [records, liveMode]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  // IDs of the most recent addition in live mode (first N where N=1 here)
  const newestId = liveMode && records.length > 0 ? records[0].id : null;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              {COLUMNS.map((col) => (
                <th
                  key={col}
                  className="px-6 py-3.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {col}
                </th>
              ))}
              {onDelete && (
                <th className="px-6 py-3.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody ref={tbodyRef} className="divide-y divide-slate-800/60">
            {loading ? (
              <SkeletonRows />
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={onDelete ? COLUMNS.length + 1 : COLUMNS.length}>
                  <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
                    <svg className="h-10 w-10 text-slate-700" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p className="text-sm text-slate-500">No records match the current filters.</p>
                  </div>
                </td>
              </tr>
            ) : (
              records.map((rec) => {
                const isNew = liveMode && rec.id === newestId;
                return (
                  <tr
                    key={rec.id}
                    data-live={isNew ? "true" : undefined}
                    className={`transition-colors hover:bg-slate-800/40 ${
                      isNew ? "bg-indigo-500/10 animate-pulse-once" : ""
                    }`}
                  >
                    <td className="px-6 py-3.5 font-medium text-slate-200">
                      {rec.student_name ?? "Unknown"}
                    </td>
                    <td className="px-6 py-3.5 font-mono text-xs text-slate-400">
                      {rec.student_code ?? "—"}
                    </td>
                    <td className="px-6 py-3.5 text-slate-400">{rec.date ?? "—"}</td>
                    <td className="px-6 py-3.5 tabular-nums text-slate-400">
                      {rec.time ? rec.time.slice(0, 5) : "—"}
                    </td>
                    <td className="px-6 py-3.5">
                      <StatusBadge status={rec.status} />
                    </td>
                    <td className="px-6 py-3.5">
                      <ConfidenceBadge band={rec.confidence_band} />
                    </td>
                    <td className="px-6 py-3.5 tabular-nums text-slate-400">
                      {rec.similarity_score != null
                        ? `${(rec.similarity_score * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    {onDelete && (
                      <td className="px-6 py-3.5">
                        <button
                          onClick={() => onDelete(rec)}
                          className="rounded-lg px-2.5 py-1 text-xs font-medium text-rose-400 ring-1 ring-rose-500/30 transition hover:bg-rose-500/10"
                        >
                          Delete
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && total > 0 && (
        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-3">
          <p className="text-xs text-slate-500">
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total} records
          </p>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => onPage?.(page - 1)}
              className="rounded-lg px-2.5 py-1.5 text-xs text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 disabled:pointer-events-none disabled:opacity-40"
            >
              ← Prev
            </button>
            <span className="px-2 text-xs text-slate-500">
              {page} / {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => onPage?.(page + 1)}
              className="rounded-lg px-2.5 py-1.5 text-xs text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 disabled:pointer-events-none disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
