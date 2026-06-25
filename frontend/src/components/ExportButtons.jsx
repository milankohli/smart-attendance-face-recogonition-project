import { useState } from "react";

// ── Small spinner ──────────────────────────────────────────────────────────
function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}

// ── Format button ──────────────────────────────────────────────────────────
function FormatButton({ format, active, onClick }) {
  return (
    <button
      type="button"
      onClick={() => onClick(format)}
      className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
        active
          ? "bg-indigo-600 text-white"
          : "bg-slate-800 text-slate-400 ring-1 ring-slate-700 hover:bg-slate-700 hover:text-slate-200"
      }`}
    >
      {format.toUpperCase()}
    </button>
  );
}

/**
 * ExportButtons
 *
 * Props:
 *   onDownload   async (opts: { format, startDate, endDate, status }) => void
 *   onPreview    async (opts: { startDate, endDate, status }) => void  (streams CSV for preview)
 *   previewData  string|null   CSV text to display in the preview pane
 *   loading      bool
 */
export default function ExportButtons({
  onDownload,
  onPreview,
  previewData = null,
  loading = false,
}) {
  const [format, setFormat] = useState("csv");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const filters = { startDate: startDate || undefined, endDate: endDate || undefined, status: status || undefined };

  const handleDownload = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      await onDownload?.({ format, ...filters });
    } finally {
      setDownloading(false);
    }
  };

  const handlePreview = async () => {
    if (previewing) return;
    setPreviewing(true);
    try {
      await onPreview?.(filters);
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
        <h3 className="mb-4 text-sm font-semibold text-slate-200">Export Options</h3>

        <div className="space-y-5">
          {/* Format toggle */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Format</p>
            <div className="flex gap-2">
              {["csv", "json"].map((f) => (
                <FormatButton key={f} format={f} active={format === f} onClick={setFormat} />
              ))}
            </div>
          </div>

          {/* Date range */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
                From
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
                To
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
              />
            </div>
          </div>

          {/* Status filter */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
              Status
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
            >
              <option value="">All statuses</option>
              <option value="present">Present</option>
              <option value="absent">Absent</option>
              <option value="late">Late</option>
              <option value="unknown">Unknown</option>
            </select>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 pt-4">
            <button
              onClick={handleDownload}
              disabled={downloading || loading}
              className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
            >
              {downloading ? <Spinner /> : (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
              )}
              Download {format.toUpperCase()}
            </button>

            {onPreview && format === "csv" && (
              <button
                onClick={handlePreview}
                disabled={previewing || loading}
                className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-slate-300 ring-1 ring-slate-700 transition hover:bg-slate-800 disabled:opacity-60"
              >
                {previewing ? <Spinner /> : (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                )}
                Preview
              </button>
            )}
          </div>
        </div>
      </div>

      {/* CSV preview pane */}
      {previewData && (
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Preview
            </h3>
            <span className="text-xs text-slate-600">
              {previewData.split("\n").length - 1} rows
            </span>
          </div>
          <pre className="max-h-80 overflow-auto p-5 text-xs leading-relaxed text-slate-300">
            {previewData}
          </pre>
        </div>
      )}
    </div>
  );
}
