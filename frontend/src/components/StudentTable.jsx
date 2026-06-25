import { useState } from "react";

// ── Status badge ───────────────────────────────────────────────────────────
function ActiveBadge({ active }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        active
          ? "bg-emerald-500/15 text-emerald-400"
          : "bg-slate-700 text-slate-400"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-400" : "bg-slate-500"}`}
      />
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────
function EmptyState({ query }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900">
        <svg className="h-7 w-7 text-slate-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-300">No students found</p>
      <p className="text-xs text-slate-500">
        {query ? `No results for "${query}"` : "Register a student to get started."}
      </p>
    </div>
  );
}

// ── Skeleton rows ──────────────────────────────────────────────────────────
function SkeletonRows({ count = 6 }) {
  return Array.from({ length: count }).map((_, i) => (
    <tr key={i}>
      {[40, 28, 20, 16, 12].map((w, j) => (
        <td key={j} className="px-6 py-3.5">
          <div className={`h-4 w-${w} animate-pulse rounded bg-slate-800`} />
        </td>
      ))}
      <td className="px-6 py-3.5">
        <div className="h-4 w-24 animate-pulse rounded bg-slate-800" />
      </td>
    </tr>
  ));
}

const COLUMNS = ["Student", "Code", "Department", "Email", "Faces", "Status", "Actions"];

/**
 * StudentTable
 *
 * Props:
 *   students  Student[]     rows to display
 *   loading   bool
 *   query     string        search query (shown in empty state)
 *   page      number
 *   pageSize  number
 *   total     number
 *   onPage    (page) => void
 *   onView    (student) => void   open detail panel
 *   onEdit    (student) => void   open edit form modal
 *   onCapture (student) => void   open face capture modal
 *   onDelete  (student) => void   open delete confirmation modal
 */
export default function StudentTable({
  students = [],
  loading = false,
  query = "",
  page = 1,
  pageSize = 50,
  total = 0,
  onPage,
  onView,
  onEdit,
  onCapture,
  onDelete,
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

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
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {loading ? (
              <SkeletonRows />
            ) : students.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length}>
                  <EmptyState query={query} />
                </td>
              </tr>
            ) : (
              students.map((s) => (
                <tr
                  key={s.id}
                  className="transition-colors hover:bg-slate-800/40"
                >
                  {/* Name + avatar initial */}
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-bold text-indigo-400">
                        {s.name?.charAt(0).toUpperCase() ?? "?"}
                      </div>
                      <span className="font-medium text-slate-200">{s.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-3.5 font-mono text-xs text-slate-300">{s.student_code}</td>
                  <td className="px-6 py-3.5 text-slate-400">{s.department ?? "—"}</td>
                  <td className="px-6 py-3.5 text-slate-400">{s.email ?? "—"}</td>
                  {/* Embedding count */}
                  <td className="px-6 py-3.5 text-slate-400">
                    {s.embedding_count != null ? (
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          s.embedding_count > 0
                            ? "bg-indigo-500/15 text-indigo-400"
                            : "bg-slate-700 text-slate-500"
                        }`}
                      >
                        {s.embedding_count}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-6 py-3.5">
                    <ActiveBadge active={s.is_active} />
                  </td>
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onView?.(s)}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
                      >
                        View
                      </button>
                      <button
                        onClick={() => onEdit?.(s)}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onCapture?.(s)}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-indigo-400 ring-1 ring-indigo-500/30 transition hover:bg-indigo-500/10 hover:text-indigo-300"
                      >
                        Capture
                      </button>
                      <button
                        onClick={() => onDelete?.(s)}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-rose-400 ring-1 ring-rose-500/30 transition hover:bg-rose-500/10 hover:text-rose-300"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && total > 0 && (
        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-3">
          <p className="text-xs text-slate-500">
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total} students
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
