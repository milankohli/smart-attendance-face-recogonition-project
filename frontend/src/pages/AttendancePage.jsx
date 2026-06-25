import { useCallback, useEffect, useState } from "react";
import AttendanceTable from "../components/AttendanceTable";
import AttendanceCameraModal from "../components/AttendanceCameraModal";
import { attendanceService } from "../services/attendanceService";
import { useRecognitionSocket } from "../websocket/recognitionSocket";

// ── Live indicator dot ─────────────────────────────────────────────────────
function LiveDot({ connected }) {
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium">
      <span
        className={`h-2 w-2 rounded-full ${
          connected ? "animate-pulse bg-emerald-400" : "bg-slate-600"
        }`}
      />
      <span className={connected ? "text-emerald-400" : "text-slate-500"}>
        {connected ? "Live" : "Offline"}
      </span>
    </span>
  );
}

// ── Filter bar ─────────────────────────────────────────────────────────────
function FilterBar({ filters, onChange, onReset }) {
  const set = (key) => (e) => onChange({ ...filters, [key]: e.target.value });
  const inputCls =
    "rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30";

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label className="mb-1 block text-xs text-slate-500">Date</label>
        <input type="date" value={filters.date} onChange={set("date")} className={inputCls} />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-500">From</label>
        <input type="date" value={filters.startDate} onChange={set("startDate")} className={inputCls} />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-500">To</label>
        <input type="date" value={filters.endDate} onChange={set("endDate")} className={inputCls} />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-500">Status</label>
        <select value={filters.status} onChange={set("status")} className={inputCls}>
          <option value="">All</option>
          <option value="Present">Present</option>
          <option value="Late">Late</option>
          <option value="Absent">Absent</option>
        </select>
      </div>
      <button
        onClick={onReset}
        className="rounded-xl px-4 py-2 text-sm text-slate-400 ring-1 ring-slate-700 hover:bg-slate-800 hover:text-slate-200"
      >
        Reset
      </button>
    </div>
  );
}

const EMPTY_FILTERS = { date: "", startDate: "", endDate: "", status: "" };

// ── Confirm delete modal ───────────────────────────────────────────────────
function DeleteModal({ record, onClose, onConfirm, loading }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <h2 className="text-sm font-semibold text-slate-100">Delete Record</h2>
        <p className="mt-2 text-sm text-slate-400">
          Remove the attendance record for{" "}
          <span className="font-medium text-slate-200">{record.student_name}</span> on{" "}
          {record.date}? This cannot be undone.
        </p>
        <div className="mt-5 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 py-2.5 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
          >
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Camera icon ────────────────────────────────────────────────────────────
function CameraIcon({ className }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"
      />
    </svg>
  );
}

const PAGE_SIZE = 50;

export default function AttendancePage() {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [liveMode, setLiveMode] = useState(false);
  const [liveRecords, setLiveRecords] = useState([]);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Camera modal state
  const [cameraOpen, setCameraOpen] = useState(false);

  // ── Fetch records ─────────────────────────────────────────────────────────
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await attendanceService.list({
        date: filters.date || undefined,
        startDate: filters.startDate || undefined,
        endDate: filters.endDate || undefined,
        status: filters.status || undefined,
        page,
        pageSize: PAGE_SIZE,
      });
      setRecords(res.items);
      setTotal(res.total);
    } catch {
      setError("Failed to load attendance records.");
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  // ── WebSocket: passive live feed ──────────────────────────────────────────
  // Used only for the "Start Live Feed" broadcast channel.
  // The camera modal uses attendanceService.identify() directly — no overlap.
  const { connected, connect, disconnect } = useRecognitionSocket({
    onEvent: (evt) => {
      if (!liveMode) return;
      if (!evt.recognized) return;
      const now = new Date();
      const synth = {
        id: Date.now(),
        student_name: evt.student_name ?? "Unknown",
        student_code: evt.student_code ?? "—",
        date: now.toISOString().slice(0, 10),
        time: now.toTimeString().slice(0, 8),
        status: evt.recognized ? "present" : "unknown",
        confidence_band: evt.confidence_band,
        similarity_score: evt.similarity,
      };
      setLiveRecords((prev) => [synth, ...prev].slice(0, 100));
    },
  });

  const toggleLive = () => {
    if (liveMode) {
      disconnect();
      setLiveMode(false);
      setLiveRecords([]);
    } else {
      connect();
      setLiveMode(true);
    }
  };

  // ── Camera modal handlers ─────────────────────────────────────────────────

  /** Called by AttendanceCameraModal when a new record is successfully created */
  const handleAttendanceMarked = useCallback(
    (record) => {
      // Optimistically prepend the new record to the table so the user sees
      // it instantly, then refetch in the background to get the canonical row.
      if (record) {
        const optimistic = {
          id: record.id ?? Date.now(),
          student_name: record.student_name ?? "—",
          student_code: record.student_code ?? "—",
          date: record.date ?? new Date().toISOString().slice(0, 10),
          time: record.time ?? new Date().toTimeString().slice(0, 8),
          status: record.status ?? "present",
          confidence_band: record.confidence_band ?? null,
          similarity_score: record.similarity_score ?? record.similarity ?? null,
        };
        setRecords((prev) => [optimistic, ...prev]);
        setTotal((t) => t + 1);
      }
      // Refetch after modal closes (slight delay lets the server settle)
      setTimeout(fetchRecords, 1_200);
    },
    [fetchRecords]
  );

  // ── Delete record ─────────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await attendanceService.delete(deleteTarget.id);
      setDeleteTarget(null);
      fetchRecords();
    } catch {
      setError("Failed to delete record.");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const displayRecords = liveMode
    ? [...liveRecords, ...records].slice(0, PAGE_SIZE)
    : records;

  return (
    <div className="space-y-6">
      {/* Camera modal */}
      {cameraOpen && (
        <AttendanceCameraModal
          onClose={() => setCameraOpen(false)}
          onMarked={handleAttendanceMarked}
        />
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Attendance</h1>
          <p className="mt-1 text-sm text-slate-400">
            {total.toLocaleString()} total records
          </p>
        </div>

        <div className="flex items-center gap-3">
          <LiveDot connected={connected} />

          {/* Mark Attendance — opens camera modal */}
          <button
            onClick={() => setCameraOpen(true)}
            disabled={cameraOpen}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-900/40 transition hover:bg-indigo-500 disabled:opacity-60"
          >
            <CameraIcon className="h-4 w-4" />
            Mark Attendance
          </button>

          {/* Live feed toggle */}
          <button
            onClick={toggleLive}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
              liveMode
                ? "bg-emerald-600/20 text-emerald-400 ring-1 ring-emerald-500/40 hover:bg-emerald-600/30"
                : "bg-slate-800 text-slate-300 ring-1 ring-slate-700 hover:bg-slate-700"
            }`}
          >
            {liveMode ? "Stop Live Feed" : "Start Live Feed"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      {/* Filters (hidden in live mode) */}
      {!liveMode && (
        <FilterBar
          filters={filters}
          onChange={(f) => {
            setFilters(f);
            setPage(1);
          }}
          onReset={() => {
            setFilters(EMPTY_FILTERS);
            setPage(1);
          }}
        />
      )}

      {/* Live mode banner */}
      {liveMode && (
        <div className="rounded-xl border border-emerald-800/30 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-400">
          Live mode active — new recognition events appear at the top of the table in real time.
        </div>
      )}

      <AttendanceTable
        records={displayRecords}
        loading={loading && !liveMode}
        liveMode={liveMode}
        page={page}
        pageSize={PAGE_SIZE}
        total={liveMode ? displayRecords.length : total}
        onPage={liveMode ? undefined : setPage}
        onDelete={(rec) => setDeleteTarget(rec)}
      />

      {deleteTarget && (
        <DeleteModal
          record={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleting}
        />
      )}
    </div>
  );
}
