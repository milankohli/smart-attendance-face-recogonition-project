/**
 * AnalyticsCharts.jsx
 * ────────────────────────────────────────────────────────────────────────────
 * Four reusable chart panels built on Chart.js (via CDN-style import).
 *
 * Requires: npm install chart.js
 *
 * Charts exported:
 *   DailyAttendanceChart      – bar: unique students per day (last 30 days)
 *   StudentFrequencyChart     – horizontal bar: days present per student
 *   MonthlyAttendanceChart    – bar: total entries per month
 *   SummaryDonut              – doughnut: present / unknown split
 * ────────────────────────────────────────────────────────────────────────────
 */
import { useEffect, useRef } from "react";
import {
  Chart,
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  ArcElement,
  DoughnutController,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";

// Register the Chart.js components we use
Chart.register(
  BarController, BarElement,
  LineController, LineElement, PointElement,
  ArcElement, DoughnutController,
  CategoryScale, LinearScale,
  Tooltip, Legend, Filler
);

// ── Design tokens matching the slate-950 theme ────────────────────────────
const INDIGO  = "rgba(99,102,241,0.85)";
const INDIGO_L= "rgba(99,102,241,0.25)";
const EMERALD = "rgba(52,211,153,0.8)";
const ROSE    = "rgba(251,113,133,0.8)";
const AMBER   = "rgba(251,191,36,0.8)";
const GRID    = "rgba(148,163,184,0.08)";
const TEXT    = "rgba(148,163,184,0.7)";

const BASE_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 400 },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: "#1e293b",
      borderColor: "#334155",
      borderWidth: 1,
      titleColor: "#e2e8f0",
      bodyColor: "#94a3b8",
      padding: 10,
      cornerRadius: 8,
    },
  },
  scales: {
    x: {
      grid: { color: GRID },
      ticks: { color: TEXT, font: { size: 11 } },
    },
    y: {
      grid: { color: GRID },
      ticks: { color: TEXT, font: { size: 11 } },
      beginAtZero: true,
    },
  },
};

// ── Generic canvas hook ────────────────────────────────────────────────────
function useChart(config) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    if (chartRef.current) chartRef.current.destroy();
    chartRef.current = new Chart(ctx, config);
    return () => chartRef.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(config.data)]); // re-render when data changes

  return canvasRef;
}

// ── Chart panel wrapper ────────────────────────────────────────────────────
function ChartPanel({ title, subtitle, children, loading }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <span className="h-7 w-7 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
        </div>
      ) : (
        <div className="relative h-56">{children}</div>
      )}
    </div>
  );
}

// ── Daily Attendance Chart ─────────────────────────────────────────────────
/**
 * Props:
 *   points   DailyAttendancePoint[]  { date, unique_students, total_entries }
 *   loading  bool
 */
export function DailyAttendanceChart({ points = [], loading = false }) {
  const labels  = points.map((p) => p.date?.slice(5)); // MM-DD
  const data1   = points.map((p) => p.unique_students);
  const data2   = points.map((p) => p.total_entries);

  const canvasRef = useChart({
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Unique Students",
          data: data1,
          backgroundColor: INDIGO,
          borderRadius: 6,
          borderSkipped: false,
        },
        {
          label: "Total Entries",
          data: data2,
          backgroundColor: INDIGO_L,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      ...BASE_OPTIONS,
      plugins: {
        ...BASE_OPTIONS.plugins,
        legend: {
          display: true,
          labels: { color: TEXT, boxWidth: 12, font: { size: 11 } },
        },
      },
    },
  });

  return (
    <ChartPanel
      title="Daily Attendance"
      subtitle="Unique students vs total entries per day"
      loading={loading}
    >
      <canvas ref={canvasRef} />
    </ChartPanel>
  );
}

// ── Student Frequency Chart ────────────────────────────────────────────────
/**
 * Props:
 *   items    StudentAttendanceFrequency[]  { student_name, days_present, … }
 *   loading  bool
 */
export function StudentFrequencyChart({ items = [], loading = false }) {
  // Sort descending, take top 15
  const top = [...items]
    .sort((a, b) => b.days_present - a.days_present)
    .slice(0, 15);

  const canvasRef = useChart({
    type: "bar",
    data: {
      labels: top.map((s) => s.student_name),
      datasets: [
        {
          label: "Days Present",
          data: top.map((s) => s.days_present),
          backgroundColor: EMERALD,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      ...BASE_OPTIONS,
      indexAxis: "y",
      scales: {
        x: { ...BASE_OPTIONS.scales.x, beginAtZero: true },
        y: { ...BASE_OPTIONS.scales.y, grid: { display: false } },
      },
    },
  });

  return (
    <ChartPanel
      title="Top Attendees"
      subtitle="Days present per student (top 15)"
      loading={loading}
    >
      <div className="relative" style={{ height: Math.max(200, top.length * 28) }}>
        <canvas ref={canvasRef} />
      </div>
    </ChartPanel>
  );
}

// ── Monthly Attendance Chart ───────────────────────────────────────────────
/**
 * Props:
 *   points   MonthlyAttendancePoint[]  { month: "YYYY-MM", total_entries }
 *   loading  bool
 */
export function MonthlyAttendanceChart({ points = [], loading = false }) {
  const canvasRef = useChart({
    type: "bar",
    data: {
      labels: points.map((p) => p.month),
      datasets: [
        {
          label: "Total Entries",
          data: points.map((p) => p.total_entries),
          backgroundColor: AMBER,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: BASE_OPTIONS,
  });

  return (
    <ChartPanel
      title="Monthly Attendance"
      subtitle="Total entries per month"
      loading={loading}
    >
      <canvas ref={canvasRef} />
    </ChartPanel>
  );
}

// ── Summary Donut ──────────────────────────────────────────────────────────
/**
 * Props:
 *   summary  AnalyticsSummary  { today_attendance_count, unknown_detections_count, … }
 *   loading  bool
 */
export function SummaryDonut({ summary, loading = false }) {
  const known   = (summary?.today_attendance_count ?? 0) - (summary?.unknown_detections_count ?? 0);
  const unknown = summary?.unknown_detections_count ?? 0;

  const canvasRef = useChart({
    type: "doughnut",
    data: {
      labels: ["Identified", "Unknown"],
      datasets: [
        {
          data: [Math.max(0, known), unknown],
          backgroundColor: [EMERALD, ROSE],
          borderColor: "#0f172a",
          borderWidth: 3,
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      cutout: "68%",
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { color: TEXT, boxWidth: 12, font: { size: 11 }, padding: 16 },
        },
        tooltip: BASE_OPTIONS.plugins.tooltip,
      },
    },
  });

  return (
    <ChartPanel
      title="Today's Recognition Split"
      subtitle="Identified vs unknown detections"
      loading={loading}
    >
      <canvas ref={canvasRef} />
    </ChartPanel>
  );
}
