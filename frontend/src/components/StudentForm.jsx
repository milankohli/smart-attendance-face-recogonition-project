import { useEffect, useState } from "react";

// ── Field wrapper ──────────────────────────────────────────────────────────
function Field({ label, required, error, children }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
        {label}
        {required && <span className="ml-1 text-rose-500">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}

// ── Input ──────────────────────────────────────────────────────────────────
function Input({ error, ...props }) {
  return (
    <input
      className={`w-full rounded-xl border bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:ring-2 ${
        error
          ? "border-rose-500/60 focus:ring-rose-500/40"
          : "border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/30"
      }`}
      {...props}
    />
  );
}

/**
 * StudentForm
 *
 * Collects student details only (name, code, email, department).
 * Face capture is handled separately via WebcamCaptureModal — no file
 * uploads or drop zones here. This keeps the form focused and matches
 * the desktop app's two-stage flow: register details, then capture face.
 *
 * Props:
 *   initialData  object|null    Prefill values when editing an existing student
 *   onSubmit     async (data: { fields }) => void
 *   onCancel     () => void
 *   loading      bool
 *   error        string|null    Server-level error to display
 *   mode         "create"|"edit"
 */
export default function StudentForm({
  initialData = null,
  onSubmit,
  onCancel,
  loading = false,
  error = null,
  mode = "create",
}) {
  const [fields, setFields] = useState({
    name: "",
    student_code: "",
    email: "",
    department: "",
  });
  const [fieldErrors, setFieldErrors] = useState({});

  // Prefill when editing
  useEffect(() => {
    if (initialData) {
      setFields({
        name: initialData.name ?? "",
        student_code: initialData.student_code ?? "",
        email: initialData.email ?? "",
        department: initialData.department ?? "",
      });
    }
  }, [initialData]);

  const set = (key) => (e) =>
    setFields((prev) => ({ ...prev, [key]: e.target.value }));

  const validate = () => {
    const errs = {};
    if (!fields.name.trim()) errs.name = "Name is required.";
    if (!fields.student_code.trim()) errs.student_code = "Student code is required.";
    if (fields.email && !/\S+@\S+\.\S+/.test(fields.email))
      errs.email = "Enter a valid email address.";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!validate()) return;
    // Note: no faceFiles — face capture happens via webcam in step 2
    onSubmit?.({ fields });
  };

  const isEdit = mode === "edit";

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {/* Server error */}
      {error && (
        <div className="rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full Name" required error={fieldErrors.name}>
          <Input
            type="text"
            placeholder="Alice Smith"
            value={fields.name}
            onChange={set("name")}
            error={fieldErrors.name}
            autoFocus
          />
        </Field>

        <Field label="Student Code" required error={fieldErrors.student_code}>
          <Input
            type="text"
            placeholder="CS-2024-001"
            value={fields.student_code}
            onChange={set("student_code")}
            error={fieldErrors.student_code}
            disabled={isEdit} // codes are immutable after creation
          />
        </Field>

        <Field label="Email" error={fieldErrors.email}>
          <Input
            type="email"
            placeholder="alice@university.edu"
            value={fields.email}
            onChange={set("email")}
            error={fieldErrors.email}
          />
        </Field>

        <Field label="Department">
          <Input
            type="text"
            placeholder="Computer Science"
            value={fields.department}
            onChange={set("department")}
          />
        </Field>
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-slate-800 pt-4">
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="rounded-xl px-5 py-2.5 text-sm font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {loading && (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
          )}
          {isEdit ? "Save Changes" : "Next: Capture Face"}
        </button>
      </div>
    </form>
  );
}
