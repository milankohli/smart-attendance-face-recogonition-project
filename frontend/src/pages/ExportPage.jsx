import { useState } from "react";
import ExportButtons from "../components/ExportButtons";
import { exportService } from "../services/exportService";

// ── Recent export record ───────────────────────────────────────────────────
function ExportLogItem({ format, timestamp, filters }) {
  const label = [
    filters.startDate && `from ${filters.startDate}`,
    filters.endDate   && `to ${filters.endDate}`,
    filters.status    && `status: ${filters.status}`,
  ]
    .filter(Boolean)
    .join(" · ") || "All records";

  return (
    <div className="flex items-center justify-between py-2.5">
      <div className="flex items-center gap-3">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
          format === "csv"
            ? "bg-emerald-500/15 text-emerald-400"
            : "bg-amber-500/15 text-amber-400"
        }`}>
          {format.toUpperCase()}
        </div>
        <div>
          <p className="text-sm font-medium text-slate-200">{label}</p>
          <p className="text-xs text-slate-500">{timestamp}</p>
        </div>
      </div>
    </div>
  );
}

export default function ExportPage() {
  const [previewData, setPreviewData] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [exportLog, setExportLog] = useState([]);
  const [error, setError] = useState("");

  const handleDownload = async ({ format, startDate, endDate, status }) => {
    setDownloading(true);
    setError("");
    const filters = { startDate, endDate, status };
    try {
      await exportService.download({ format, ...filters });
      const timestamp = new Date().toLocaleTimeString();
      setExportLog((prev) => [{ format, timestamp, filters }, ...prev].slice(0, 8));
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Export failed. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

  const handlePreview = async ({ startDate, endDate, status }) => {
    setError("");
    try {
      const csv = await exportService.streamCSV({ startDate, endDate, status });
      setPreviewData(csv);
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Preview failed.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">Export</h1>
        <p className="mt-1 text-sm text-slate-400">
          Download attendance records in CSV or JSON format, with optional filters.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <ExportButtons
        onDownload={handleDownload}
        onPreview={handlePreview}
        previewData={previewData}
        loading={downloading}
      />

      {/* Export log */}
      {exportLog.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
          <div className="border-b border-slate-800 px-6 py-4">
            <h3 className="text-sm font-semibold text-slate-200">Recent Exports</h3>
          </div>
          <div className="divide-y divide-slate-800/60 px-6">
            {exportLog.map((entry, i) => (
              <ExportLogItem key={i} {...entry} />
            ))}
          </div>
        </div>
      )}

      {/* Info card */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          About Exports
        </h3>
        <ul className="space-y-2 text-sm text-slate-400">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-indigo-400">→</span>
            <span><strong className="font-medium text-slate-300">CSV</strong> — compatible with Excel, Google Sheets, and any spreadsheet tool.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-indigo-400">→</span>
            <span><strong className="font-medium text-slate-300">JSON</strong> — structured format for programmatic processing or import into other systems.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-indigo-400">→</span>
            <span>Use the <strong className="font-medium text-slate-300">Preview</strong> button to inspect CSV data before downloading.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-indigo-400">→</span>
            <span>Leave date fields blank to export all records across all dates.</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
