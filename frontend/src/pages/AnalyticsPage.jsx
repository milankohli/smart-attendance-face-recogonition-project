import { useCallback, useEffect, useState } from "react";
import StatCard from "../components/StatCard";
import {
  DailyAttendanceChart,
  MonthlyAttendanceChart,
  StudentFrequencyChart,
  SummaryDonut,
} from "../components/AnalyticsCharts";
import { analyticsService } from "../services/analyticsService";

// ── Inline icons ───────────────────────────────────────────────────────────
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
  { key: "total_students",           title: "Registered Students",  accent: "bg-indigo-500/15 text-indigo-400",  icon: Icons.users   },
  { key: "today_attendance_count",   title: "Today's Attendance",   accent: "bg-emerald-500/15 text-emerald-400", icon: Icons.check   },
  { key: "total_attendance_records", title: "Total Records",        accent: "bg-sky-500/15 text-sky-400",         icon: Icons.archive },
  { key: "unknown_detections_count", title: "Unknown Detections",   accent: "bg-rose-500/15 text-rose-400",       icon: Icons.alert   },
];

// ── Range quick-selects ────────────────────────────────────────────────────
function rangeFor(preset) {
  const today = new Date();
  const fmt = (d) => d.toISOString().slice(0, 10);
  const shift = (days) => { const d = new Date(today); d.setDate(d.getDate() - days); return fmt(d); };
  switch (preset) {
    case "7d":  return { startDate: shift(6),  endDate: fmt(today) };
    case "30d": return { startDate: shift(29), endDate: fmt(today) };
    case "90d": return { startDate: shift(89), endDate: fmt(today) };
    default:    return { startDate: shift(29), endDate: fmt(today) };
  }
}

export default function AnalyticsPage() {
  const [summary, setSummary]     = useState(null);
  const [daily,   setDaily]       = useState(null);
  const [byStudent, setByStudent] = useState(null);
  const [monthly, setMonthly]     = useState(null);

  const [summaryLoading,    setSummaryLoading]    = useState(true);
  const [dailyLoading,      setDailyLoading]      = useState(true);
  const [byStudentLoading,  setByStudentLoading]  = useState(true);
  const [monthlyLoading,    setMonthlyLoading]    = useState(true);

  const [error, setError] = useState("");
  const [preset, setPreset] = useState("30d");

  const { startDate, endDate } = rangeFor(preset);
  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState(currentYear);

  // ── Fetch all ─────────────────────────────────────────────────────────────
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try { setSummary(await analyticsService.getSummary()); }
    catch { setError("Failed to load summary."); }
    finally { setSummaryLoading(false); }
  }, []);

  const fetchDaily = useCallback(async () => {
    setDailyLoading(true);
    try { setDaily(await analyticsService.getDaily(startDate, endDate)); }
    catch { /* non-fatal */ }
    finally { setDailyLoading(false); }
  }, [startDate, endDate]);

  const fetchByStudent = useCallback(async () => {
    setByStudentLoading(true);
    try { setByStudent(await analyticsService.getByStudent({ startDate, endDate, limit: 20 })); }
    catch { /* non-fatal */ }
    finally { setByStudentLoading(false); }
  }, [startDate, endDate]);

  const fetchMonthly = useCallback(async () => {
    setMonthlyLoading(true);
    try { setMonthly(await analyticsService.getMonthly(selectedYear)); }
    catch { /* non-fatal */ }
    finally { setMonthlyLoading(false); }
  }, [selectedYear]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchDaily(); fetchByStudent(); }, [fetchDaily, fetchByStudent]);
  useEffect(() => { fetchMonthly(); }, [fetchMonthly]);

  const handleRefresh = () => {
    fetchSummary();
    fetchDaily();
    fetchByStudent();
    fetchMonthly();
  };

  const years = Array.from({ length: 5 }, (_, i) => currentYear - i);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Analytics</h1>
          <p className="mt-1 text-sm text-slate-400">Attendance trends and statistics</p>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 self-start rounded-xl px-4 py-2.5 text-sm font-medium text-slate-300 ring-1 ring-slate-700 transition hover:bg-slate-800 sm:self-auto"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STAT_CONFIG.map((cfg) => (
          <StatCard
            key={cfg.key}
            title={cfg.title}
            value={summary?.[cfg.key]}
            icon={cfg.icon}
            accent={cfg.accent}
            loading={summaryLoading}
          />
        ))}
      </div>

      {/* Date range selector for daily / by-student charts */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">Range:</span>
        {["7d", "30d", "90d"].map((p) => (
          <button
            key={p}
            onClick={() => setPreset(p)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              preset === p
                ? "bg-indigo-600 text-white"
                : "bg-slate-800 text-slate-400 ring-1 ring-slate-700 hover:bg-slate-700 hover:text-slate-200"
            }`}
          >
            {p === "7d" ? "7 days" : p === "30d" ? "30 days" : "90 days"}
          </button>
        ))}
      </div>

      {/* Charts grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        <DailyAttendanceChart
          points={daily?.points ?? []}
          loading={dailyLoading}
        />
        <SummaryDonut
          summary={summary}
          loading={summaryLoading}
        />
        <StudentFrequencyChart
          items={byStudent?.items ?? []}
          loading={byStudentLoading}
        />
        {/* Monthly — has its own year selector */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">Year:</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500"
            >
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
          <MonthlyAttendanceChart
            points={monthly?.points ?? []}
            loading={monthlyLoading}
          />
        </div>
      </div>
    </div>
  );
}
