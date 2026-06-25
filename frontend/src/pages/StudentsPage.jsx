import { useCallback, useEffect, useRef, useState } from "react";
import StudentForm from "../components/StudentForm";
import StudentTable from "../components/StudentTable";
import WebcamCaptureModal from "../components/WebcamCaptureModal";
import { studentService } from "../services/studentService";

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─────────────────────────────────────────────────────────────────────────────
// Toast notification (auto-dismisses after 4 s)
// ─────────────────────────────────────────────────────────────────────────────

function Toast({ message, type = "success", onDismiss }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const styles =
    type === "success"
      ? "border-emerald-800/40 bg-emerald-950/60 text-emerald-300"
      : "border-rose-800/40 bg-rose-950/60 text-rose-300";

  return (
    <div
      className={`fixed bottom-6 right-6 z-[60] flex max-w-sm items-start gap-3 rounded-2xl border px-5 py-4 shadow-2xl backdrop-blur-sm ${styles}`}
    >
      {type === "success" ? (
        <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      ) : (
        <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      )}
      <p className="text-sm font-medium leading-snug">{message}</p>
      <button
        onClick={onDismiss}
        className="ml-auto shrink-0 opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Modal shell — shared wrapper for all overlay dialogs
// ─────────────────────────────────────────────────────────────────────────────

function Modal({ children, onClose, maxWidth = "max-w-lg" }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className={`w-full ${maxWidth} rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl`}>
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ title, subtitle, onClose }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-800 px-6 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      <button
        onClick={onClose}
        className="ml-4 mt-0.5 rounded-lg p-1 text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
        aria-label="Close"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Student Form Modal — create or edit
// ─────────────────────────────────────────────────────────────────────────────

function StudentFormModal({ student, onClose, onSuccess }) {
  const isEdit = Boolean(student);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  const handleSubmit = async ({ fields }) => {
    setSubmitting(true);
    setServerError(null);
    try {
      if (isEdit) {
        await studentService.update(student.id, {
          name: fields.name,
          email: fields.email || null,
          department: fields.department || null,
        });
        onSuccess(null, `${fields.name} updated successfully.`);
      } else {
        const created = await studentService.create({
          name: fields.name,
          student_code: fields.student_code,
          email: fields.email || null,
          department: fields.department || null,
        });
        onSuccess(created, `${fields.name} registered successfully.`);
      }
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 409) {
        setServerError("Student code already exists. Use a different student code.");
      } else {
        setServerError(detail ?? "Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal onClose={onClose} maxWidth="max-w-2xl">
      <ModalHeader
        title={isEdit ? "Edit Student" : "Register New Student"}
        subtitle={isEdit ? student.name : "Fill in the details below to create a student record."}
        onClose={onClose}
      />
      <div className="p-6">
        <StudentForm
          initialData={student ?? null}
          mode={isEdit ? "edit" : "create"}
          onSubmit={handleSubmit}
          onCancel={onClose}
          loading={submitting}
          error={serverError}
        />
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Student Detail Modal — view all info + embedding count
// ─────────────────────────────────────────────────────────────────────────────

function DetailRow({ label, value }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="w-32 shrink-0 text-xs font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className="text-sm text-slate-200 break-all">{value ?? "—"}</dd>
    </div>
  );
}

function StudentDetailModal({ student, onClose, onEdit, onCapture, onDelete }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await studentService.get(student.id);
        if (!cancelled) setDetail(data);
      } catch {
        if (!cancelled) setError("Failed to load student details.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [student.id]);

  const s = detail ?? student;

  return (
    <Modal onClose={onClose} maxWidth="max-w-xl">
      <ModalHeader
        title="Student Details"
        subtitle={`ID ${student.id}`}
        onClose={onClose}
      />

      <div className="p-6">
        {error && (
          <div className="mb-4 rounded-xl border border-rose-800/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        {/* Avatar + name hero */}
        <div className="mb-6 flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-indigo-500/20 text-xl font-bold text-indigo-400">
            {s.name?.charAt(0).toUpperCase() ?? "?"}
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-100">{s.name}</p>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                s.is_active
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-slate-700 text-slate-400"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${s.is_active ? "bg-emerald-400" : "bg-slate-500"}`} />
              {s.is_active ? "Active" : "Inactive"}
            </span>
          </div>
        </div>

        {/* Details list */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-5 animate-pulse rounded bg-slate-800" />
            ))}
          </div>
        ) : (
          <dl className="space-y-3 rounded-xl border border-slate-800 bg-slate-800/30 p-4">
            <DetailRow label="Student Code" value={s.student_code} />
            <DetailRow label="Email" value={s.email} />
            <DetailRow label="Department" value={s.department} />
            <DetailRow
              label="Face Samples"
              value={
                detail?.embedding_count != null
                  ? `${detail.embedding_count} sample${detail.embedding_count !== 1 ? "s" : ""}`
                  : s.embedding_count != null
                  ? `${s.embedding_count} sample${s.embedding_count !== 1 ? "s" : ""}`
                  : "—"
              }
            />
            {s.created_at && (
              <DetailRow
                label="Registered"
                value={new Date(s.created_at).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              />
            )}
          </dl>
        )}

        {/* Action buttons */}
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            onClick={() => { onClose(); onEdit(s); }}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slate-300 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-100"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
            </svg>
            Edit
          </button>
          <button
            onClick={() => { onClose(); onCapture(s); }}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-indigo-400 ring-1 ring-indigo-500/30 transition hover:bg-indigo-500/10 hover:text-indigo-300"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
            </svg>
            Add Face Samples
          </button>
          <button
            onClick={() => { onClose(); onDelete(s); }}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-rose-400 ring-1 ring-rose-500/30 transition hover:bg-rose-500/10 hover:text-rose-300"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
            Delete
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Face Capture Modal
// ─────────────────────────────────────────────────────────────────────────────

function CaptureModal({ student, onClose, onSuccess }) {
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const handleFiles = (e) => {
    const picked = Array.from(e.target.files).filter((f) => f.type.startsWith("image/"));
    setFiles((prev) => [...prev, ...picked]);
    e.target.value = "";
  };

  const handleUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    setError("");
    try {
      const result = await studentService.captureFaceBatch(student.id, files);
      onSuccess(`${result.length} face sample${result.length !== 1 ? "s" : ""} saved for ${student.name}.`);
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <ModalHeader
        title="Add Face Samples"
        subtitle={student.name}
        onClose={onClose}
      />
      <div className="space-y-4 p-6">
        {error && (
          <div className="rounded-xl border border-rose-800/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        <button
          onClick={() => inputRef.current?.click()}
          className="w-full rounded-xl border-2 border-dashed border-slate-700 py-8 text-center text-sm text-slate-400 transition hover:border-indigo-500/60 hover:text-slate-200"
        >
          <svg className="mx-auto mb-2 h-7 w-7 text-slate-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          Click to select face images
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleFiles}
        />

        {files.length > 0 && (
          <div>
            <p className="mb-2 text-xs text-slate-500">{files.length} file{files.length !== 1 ? "s" : ""} selected</p>
            <div className="flex flex-wrap gap-2">
              {files.map((f, i) => (
                <div key={i} className="relative">
                  <img
                    src={URL.createObjectURL(f)}
                    alt={f.name}
                    className="h-16 w-16 rounded-xl object-cover ring-1 ring-slate-700"
                  />
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 text-xs text-white shadow"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!files.length || uploading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
          >
            {uploading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            Upload{files.length > 0 ? ` (${files.length})` : ""}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Delete Confirm Modal
// ─────────────────────────────────────────────────────────────────────────────

function DeleteModal({ student, onClose, onConfirm, loading }) {
  return (
    <Modal onClose={onClose} maxWidth="max-w-sm">
      <div className="p-6">
        {/* Icon */}
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-rose-500/10">
          <svg className="h-5 w-5 text-rose-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
          </svg>
        </div>

        <h2 className="text-sm font-semibold text-slate-100">Delete Student</h2>
        <p className="mt-2 text-sm text-slate-400">
          Delete{" "}
          <span className="font-medium text-slate-200">{student.name}</span>? Face embeddings
          will be removed and the student record will be permanently deleted. Attendance
          history will be preserved.
        </p>

        <div className="mt-5 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:opacity-60"
          >
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            Delete
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export default function StudentsPage() {
  // ── List state ────────────────────────────────────────────────────────
  const [students, setStudents] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("");
  const debouncedQuery = useDebounce(query, 400);
  const debouncedDept = useDebounce(department, 400);

  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");

  // ── Modal state ───────────────────────────────────────────────────────
  const [formTarget, setFormTarget] = useState(null); // null → closed; false → create; Student → edit
  const [viewTarget, setViewTarget] = useState(null);
  const [captureTarget, setCaptureTarget] = useState(null);
  const [webcamTarget, setWebcamTarget] = useState(null); // Student | null — post-create webcam capture
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // ── Toast ─────────────────────────────────────────────────────────────
  const [toast, setToast] = useState(null); // { message, type }
  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
  }, []);

  // ── Data fetching ─────────────────────────────────────────────────────
  const fetchStudents = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      const res = await studentService.list({
        department: debouncedDept || undefined,
        page,
        pageSize: PAGE_SIZE,
      });
      setStudents(res.items);
      setTotal(res.total);
    } catch {
      setListError("Failed to load students. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [debouncedDept, page]);

  // Reset to page 1 when department filter changes
  useEffect(() => {
    setPage(1);
  }, [debouncedDept]);

  useEffect(() => {
    fetchStudents();
  }, [fetchStudents]);

  // Client-side name/code search filter (snappy, no extra round-trip)
  const filtered = debouncedQuery
    ? students.filter(
        (s) =>
          s.name.toLowerCase().includes(debouncedQuery.toLowerCase()) ||
          s.student_code.toLowerCase().includes(debouncedQuery.toLowerCase())
      )
    : students;

  // ── Action handlers ───────────────────────────────────────────────────

  const handleFormSuccess = useCallback(
    (createdStudent, message) => {
      setFormTarget(null);
      if (createdStudent) {
        // CREATE flow: student was just created — open webcam capture immediately.
        showToast(message);
        setWebcamTarget(createdStudent);
      } else {
        // EDIT flow: no face capture step needed, just refresh and toast.
        fetchStudents();
        showToast(message);
      }
    },
    [fetchStudents, showToast]
  );

  const handleCaptureSuccess = useCallback(
    (message) => {
      setCaptureTarget(null);
      fetchStudents();
      showToast(message);
    },
    [fetchStudents, showToast]
  );

  const handleWebcamComplete = useCallback(() => {
    const name = webcamTarget?.name ?? "Student";
    setWebcamTarget(null);
    fetchStudents();
    showToast(`Face samples captured successfully for ${name}.`);
  }, [webcamTarget, fetchStudents, showToast]);

  const handleWebcamCancel = useCallback(() => {
    setWebcamTarget(null);
    fetchStudents();
  }, [fetchStudents]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await studentService.delete(deleteTarget.id);
      const name = deleteTarget.name;
      // Optimistically remove from local list for immediate feedback
      setStudents((prev) => prev.filter((s) => s.id !== deleteTarget.id));
      setTotal((prev) => Math.max(0, prev - 1));
      setDeleteTarget(null);
      showToast(`${name} has been permanently deleted.`);
    } catch {
      setDeleteTarget(null);
      showToast("Failed to delete student. Please try again.", "error");
    } finally {
      setDeleting(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Students</h1>
          <p className="mt-1 text-sm text-slate-400">
            {loading ? "Loading…" : `${total} registered`}
          </p>
        </div>
        <button
          onClick={() => setFormTarget(false)}
          className="flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 sm:self-auto"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Register Student
        </button>
      </div>

      {/* ── List error (persistent, not a toast) ────────────────────── */}
      {listError && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span>{listError}</span>
        </div>
      )}

      {/* ── Filters ─────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative sm:max-w-xs w-full">
          <svg className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 15.803a7.5 7.5 0 0010.607 0z" />
          </svg>
          <input
            type="search"
            placeholder="Search by name or code…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-800 py-2.5 pl-10 pr-4 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
          />
        </div>
        <input
          type="text"
          placeholder="Filter by department…"
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 sm:max-w-52"
        />
        {(query || department) && (
          <button
            onClick={() => { setQuery(""); setDepartment(""); }}
            className="self-start rounded-xl px-4 py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200 sm:self-auto"
          >
            Clear
          </button>
        )}
      </div>

      {/* ── Table ───────────────────────────────────────────────────── */}
      <StudentTable
        students={filtered}
        loading={loading}
        query={debouncedQuery}
        page={page}
        pageSize={PAGE_SIZE}
        total={debouncedQuery ? filtered.length : total}
        onPage={(p) => setPage(p)}
        onView={(s) => setViewTarget(s)}
        onEdit={(s) => setFormTarget(s)}
        onCapture={(s) => setCaptureTarget(s)}
        onDelete={(s) => setDeleteTarget(s)}
      />

      {/* ── Modals ──────────────────────────────────────────────────── */}

      {/* Create / Edit form */}
      {formTarget !== null && (
        <StudentFormModal
          student={formTarget || null}
          onClose={() => setFormTarget(null)}
          onSuccess={handleFormSuccess}
        />
      )}

      {/* Detail view */}
      {viewTarget && (
        <StudentDetailModal
          student={viewTarget}
          onClose={() => setViewTarget(null)}
          onEdit={(s) => { setViewTarget(null); setFormTarget(s); }}
          onCapture={(s) => { setViewTarget(null); setCaptureTarget(s); }}
          onDelete={(s) => { setViewTarget(null); setDeleteTarget(s); }}
        />
      )}

      {/* Face capture — file upload (from table Capture button) */}
      {captureTarget && (
        <CaptureModal
          student={captureTarget}
          onClose={() => setCaptureTarget(null)}
          onSuccess={handleCaptureSuccess}
        />
      )}

      {/* Webcam face capture — auto-opened after student creation */}
      {webcamTarget && (
        <WebcamCaptureModal
          studentId={webcamTarget.id}
          studentName={webcamTarget.name}
          onComplete={handleWebcamComplete}
          onCancel={handleWebcamCancel}
        />
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <DeleteModal
          student={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleting}
        />
      )}

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}
