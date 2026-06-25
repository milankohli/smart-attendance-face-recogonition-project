/**
 * src/pages/ViewerDashboardPage.jsx
 *
 * Self-contained portal for VIEWER accounts (registered persons).
 *
 * Shows:
 *  • Profile card — name, username, email, role badge
 *  • Attendance summary cards — present / late / absent counts
 *  • Recent attendance table — date, time, status
 *
 * Fetches data from the existing /attendance endpoints.
 * Expected query-param convention: ?student_code=<username>
 * Adjust the API call to match your actual attendance router if different.
 *
 * This page has its own full-screen layout (no DashboardLayout sidebar)
 * because viewers must never see admin navigation items.
 */

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { attendanceService } from "../services/attendanceService";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year:  "numeric",
    month: "short",
    day:   "numeric",
  });
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", {
    hour:   "2-digit",
    minute: "2-digit",
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const map = {
    present: "bg-emerald-500/15 text-emerald-400 ring-emerald-500/30",
    late:    "bg-amber-500/15 text-amber-400 ring-amber-500/30",
    absent:  "bg-rose-500/15 text-rose-400 ring-rose-500/30",
  };
  const key = status?.toLowerCase() ?? "";
  const cls = map[key] ?? "bg-slate-700 text-slate-400 ring-slate-600/30";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ring-1 ${cls}`}>
      {status ?? "—"}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary stat card
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({ label, value, accent }) {
  const accents = {
    emerald: "border-emerald-800/40 bg-emerald-950/20",
    amber:   "border-amber-800/40 bg-amber-950/20",
    rose:    "border-rose-800/40 bg-rose-950/20",
    indigo:  "border-indigo-800/40 bg-indigo-950/20",
  };
  const textAccents = {
    emerald: "text-emerald-400",
    amber:   "text-amber-400",
    rose:    "text-rose-400",
    indigo:  "text-indigo-400",
  };
  return (
    <div className={`rounded-2xl border p-5 ${accents[accent] ?? "border-slate-800 bg-slate-900"}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${textAccents[accent] ?? "text-white"}`}>
        {value ?? <span className="text-slate-600">—</span>}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton loader
// ─────────────────────────────────────────────────────────────────────────────

function Skeleton({ className }) {
  return <div className={`animate-pulse rounded-lg bg-slate-800 ${className}`} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function ViewerDashboardPage() {
  const { user, logout } = useAuth();

  // Attendance data
  const [records,  setRecords]  = useState([]);
  const [summary,  setSummary]  = useState({ present: 0, late: 0, absent: 0, percentage: null });
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  // ── Fetch attendance ───────────────────────────────────────────────────────

  const fetchAttendance = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      /**
       * GET /attendance/me — scoped to the authenticated viewer.
       * The backend reads student_id from the JWT; no client parameter is sent.
       * Fetches up to 200 records (one academic term), enough for a full
       * monthly summary without a second request.
       */
      const data = await attendanceService.listMine({ page: 1, pageSize: 200 });

      const items = Array.isArray(data) ? data : (data.items ?? []);
      // Sort descending by date so the table shows most-recent first.
      items.sort((a, b) => {
        const da = a.date ?? a.marked_at ?? a.created_at ?? "";
        const db = b.date ?? b.marked_at ?? b.created_at ?? "";
        return db.localeCompare(da);
      });
      setRecords(items);

      // Compute summary exclusively from the viewer's own records.
      const counts = { present: 0, late: 0, absent: 0 };
      for (const r of items) {
        const s = r.status?.toLowerCase();
        if (s === "present") counts.present += 1;
        else if (s === "late") counts.late += 1;
        else if (s === "absent") counts.absent += 1;
      }

      // Attendance percentage = (present + late) / total × 100
      const total = counts.present + counts.late + counts.absent;
      const percentage =
        total > 0
          ? Math.round(((counts.present + counts.late) / total) * 100)
          : null;

      setSummary({ ...counts, percentage });
    } catch (err) {
      // 404 usually means no records yet — treat as empty rather than an error.
      if (err?.response?.status === 404) {
        setRecords([]);
        setSummary({ present: 0, late: 0, absent: 0, percentage: null });
      } else {
        setError("Could not load attendance data. Please try again later.");
      }
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { fetchAttendance(); }, [fetchAttendance]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">

      {/* Background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/4 top-0 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-indigo-700/6 blur-3xl" />
      </div>

      {/* ── Top bar ── */}
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
              <svg className="h-4 w-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
              </svg>
            </div>
            <span className="text-sm font-semibold tracking-tight text-white">Smart Attendance</span>
          </div>

          {/* Sign out */}
          <button
            onClick={logout}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
            Sign out
          </button>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="relative mx-auto max-w-5xl space-y-8 px-6 py-10">

        {/* Page title */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">My Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">Your profile and attendance overview.</p>
        </div>

        {/* ── Profile card ── */}
        <section>
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Profile
          </h2>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
              {/* Avatar */}
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-indigo-600/20 text-2xl font-bold text-indigo-300 ring-1 ring-indigo-500/30">
                {user?.username?.[0]?.toUpperCase() ?? "?"}
              </div>

              {/* Details */}
              <div className="flex-1 space-y-1">
                <p className="text-lg font-semibold text-white">
                  {user?.username ?? "—"}
                </p>
                <p className="text-sm text-slate-400">
                  {user?.email ?? <span className="italic text-slate-600">No email on file</span>}
                </p>
                <div className="pt-1">
                  <span className="inline-flex rounded-full bg-slate-700 px-2.5 py-0.5 text-xs font-semibold capitalize text-slate-300 ring-1 ring-slate-600/30">
                    {user?.role ?? "viewer"}
                  </span>
                </div>
              </div>

              {/* Meta */}
              <div className="space-y-1 text-right text-xs text-slate-500 sm:shrink-0">
                {user?.last_login && (
                  <p>
                    Last login:{" "}
                    <span className="text-slate-400">{formatDate(user.last_login)}</span>
                  </p>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* ── Attendance summary ── */}
        <section>
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Attendance Summary
          </h2>

          {loading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Present"    value={summary.present}    accent="emerald" />
              <StatCard label="Late"       value={summary.late}       accent="amber"   />
              <StatCard label="Absent"     value={summary.absent}     accent="rose"    />
              <StatCard
                label="Attendance %"
                value={summary.percentage !== null ? `${summary.percentage}%` : "—"}
                accent="indigo"
              />
            </div>
          )}
        </section>

        {/* ── Error ── */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
            <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* ── Recent attendance table ── */}
        <section>
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Recent Attendance
          </h2>

          {loading ? (
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
              <div className="space-y-3 p-6">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            </div>
          ) : records.length === 0 ? (
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800">
                  <svg className="h-7 w-7 text-slate-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 9v7.5" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-slate-400">No attendance records yet</p>
                <p className="text-xs text-slate-600">Records will appear here after attendance is marked.</p>
              </div>
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800">
                      {["Date", "Time", "Status"].map((h) => (
                        <th
                          key={h}
                          className="px-5 py-3.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {records.map((r, i) => (
                      <tr key={r.id ?? i} className="transition-colors hover:bg-slate-800/50">
                        <td className="px-5 py-3.5 text-slate-300">
                          {formatDate(r.date ?? r.marked_at ?? r.created_at)}
                        </td>
                        <td className="px-5 py-3.5 text-slate-400">
                          {formatTime(r.marked_at ?? r.created_at)}
                        </td>
                        <td className="px-5 py-3.5">
                          <StatusBadge status={r.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* Footer note */}
        <p className="pb-4 text-center text-xs text-slate-700">
          Smart Attendance System · Face Recognition
        </p>
      </main>
    </div>
  );
}
