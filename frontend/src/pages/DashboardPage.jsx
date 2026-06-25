import { useEffect, useState } from "react";
import StatCard from "../components/StatCard";
import api from "../services/api";

// ── Icons (inline SVGs keep the bundle dependency-free) ───────────────────
const Icons = {
  users: (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.75} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a4 4 0 00-5-3.87M9 20H4v-2a4 4 0 015-3.87m0 0a4 4 0 116 0M12 12a4 4 0 100-8 4 4 0 000 8z" />
    </svg>
  ),
  check: (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.75} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  archive: (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.75} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
    </svg>
  ),
  alert: (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.75} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
};

const STAT_CONFIG = [
  {
    key: "total_students",
    title: "Registered Students",
    accent: "bg-indigo-500/15 text-indigo-400",
    icon: Icons.users,
  },
  {
    key: "present_count",
    title: "Present",
    accent: "bg-emerald-500/15 text-emerald-400",
    icon: Icons.check,
  },
  {
    key: "late_count",
    title: "Late",
    accent: "bg-amber-500/15 text-amber-400",
    icon: Icons.archive,
  },
  {
    key: "absent_count",
    title: "Absent",
    accent: "bg-rose-500/15 text-rose-400",
    icon: Icons.alert,
  },
];

function formatLocalDate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDisplayDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [attendanceDate, setAttendanceDate] = useState("");
  const [loadingStats, setLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState("");

  const [recentAttendance, setRecentAttendance] = useState([]);
  const [loadingRecent, setLoadingRecent] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/analytics/summary");
        setSummary(data);
        setAttendanceDate(data.attendance_date ?? formatLocalDate());
      } catch {
        setStatsError("Could not load summary stats.");
        setAttendanceDate(formatLocalDate());
      } finally {
        setLoadingStats(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!attendanceDate) return;

    (async () => {
      try {
        const { data } = await api.get("/attendance", {
          params: { date: attendanceDate, page_size: 8 },
        });
        setRecentAttendance(data.items ?? []);
      } catch {
        // Non-fatal; table stays empty
      } finally {
        setLoadingRecent(false);
      }
    })();
  }, [attendanceDate]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          {new Date().toLocaleDateString("en-US", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </div>

      {/* Error banner */}
      {statsError && (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          {statsError}
        </div>
      )}

      {/* Stat cards grid */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STAT_CONFIG.map((cfg) => (
          <StatCard
            key={cfg.key}
            title={cfg.title}
            value={summary?.[cfg.key]}
            icon={cfg.icon}
            accent={cfg.accent}
            loading={loadingStats}
          />
        ))}
      </div>

      {/* Recent attendance table */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">
            {attendanceDate ? `Attendance for ${formatDisplayDate(attendanceDate)}` : "Attendance"}
          </h2>
          <a
            href="/attendance"
            className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
          >
            View all →
          </a>
        </div>

        {loadingRecent ? (
          <div className="space-y-3 p-6">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-slate-800" />
            ))}
          </div>
        ) : recentAttendance.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
            <svg className="h-10 w-10 text-slate-700" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm text-slate-500">No attendance records yet today.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  {["Student", "Code", "Time", "Status", "Similarity"].map((h) => (
                    <th
                      key={h}
                      className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {recentAttendance.map((rec) => (
                  <tr key={rec.id} className="transition-colors hover:bg-slate-800/50">
                    <td className="px-6 py-3 font-medium text-slate-200">
                      {rec.student_name ?? "—"}
                    </td>
                    <td className="px-6 py-3 text-slate-400">{rec.student_code ?? "—"}</td>
                    <td className="px-6 py-3 text-slate-400">
                      {rec.time ? rec.time.slice(0, 5) : "—"}
                    </td>
                    <td className="px-6 py-3">
                      <StatusBadge status={rec.status} />
                    </td>
                    <td className="px-6 py-3 text-slate-400">
                      {rec.similarity_score != null
                        ? `${(rec.similarity_score * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    present:  "bg-emerald-500/15 text-emerald-400",
    absent:   "bg-slate-700 text-slate-400",
    unknown:  "bg-rose-500/15 text-rose-400",
    late:     "bg-amber-500/15 text-amber-400",
  };
  const cls = map[status?.toLowerCase()] ?? "bg-slate-700 text-slate-400";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${cls}`}>
      {status ?? "unknown"}
    </span>
  );
}
