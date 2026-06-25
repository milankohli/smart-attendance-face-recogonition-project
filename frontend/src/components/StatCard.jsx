/**
 * StatCard — one summary metric tile on the dashboard.
 *
 * Props:
 *   title      string   Label beneath the value
 *   value      string | number
 *   icon       ReactNode   Icon element (e.g. from lucide-react or heroicons)
 *   accent     string   Tailwind color class applied to the icon backdrop
 *                       e.g. "bg-indigo-500/15 text-indigo-400"
 *   trend      object   Optional { value: "+12%", positive: true }
 *   loading    bool
 */
export default function StatCard({ title, value, icon, accent = "bg-slate-700 text-slate-300", trend, loading }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg transition-shadow hover:shadow-indigo-950/40">
      {/* Subtle gradient bleed in top-right corner */}
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-indigo-600/5 blur-2xl" />

      <div className="flex items-start justify-between gap-4">
        {/* Icon pill */}
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${accent}`}>
          {icon}
        </div>

        {/* Trend badge */}
        {trend && (
          <span
            className={`mt-0.5 rounded-full px-2 py-0.5 text-xs font-semibold ${
              trend.positive
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-rose-500/15 text-rose-400"
            }`}
          >
            {trend.value}
          </span>
        )}
      </div>

      <div className="mt-4">
        {loading ? (
          <div className="h-8 w-24 animate-pulse rounded-md bg-slate-800" />
        ) : (
          <p className="text-3xl font-bold tracking-tight text-white">
            {value ?? "—"}
          </p>
        )}
        <p className="mt-1 text-sm font-medium text-slate-400">{title}</p>
      </div>
    </div>
  );
}
