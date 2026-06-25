import { useState } from "react";
import { useNavigate } from "react-router-dom";
import StudentForm from "../components/StudentForm";
import WebcamCaptureModal from "../components/WebcamCaptureModal";
import { studentService } from "../services/studentService";

// ── Step indicator ─────────────────────────────────────────────────────────
function Steps({ current }) {
  const steps = ["Details", "Face Capture", "Done"];
  return (
    <div className="flex items-center gap-0">
      {steps.map((label, i) => {
        const idx = i + 1;
        const done = idx < current;
        const active = idx === current;
        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition ${
                  done
                    ? "bg-emerald-500 text-white"
                    : active
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-800 text-slate-500 ring-1 ring-slate-700"
                }`}
              >
                {done ? "✓" : idx}
              </div>
              <span
                className={`mt-1 text-xs ${
                  active ? "text-indigo-400 font-medium" : "text-slate-500"
                }`}
              >
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`mx-3 mb-4 h-px w-12 sm:w-20 ${
                  done ? "bg-emerald-500/50" : "bg-slate-800"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Webcam icon ────────────────────────────────────────────────────────────
function WebcamIcon({ className }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
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

export default function RegisterStudentPage() {
  const navigate = useNavigate();

  // Step state: 1 = details form, 2 = webcam capture, 3 = done
  const [step, setStep] = useState(1);
  const [createdStudent, setCreatedStudent] = useState(null);

  // Step 1 state
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState(null);

  // Step 2 state
  const [webcamOpen, setWebcamOpen] = useState(false);
  const [captureError, setCaptureError] = useState("");

  // ── Step 1: Create student record ────────────────────────────────────────
  const handleCreate = async ({ fields }) => {
    setFormLoading(true);
    setFormError(null);
    try {
      const student = await studentService.create({
        name: fields.name,
        student_code: fields.student_code,
        email: fields.email || undefined,
        department: fields.department || undefined,
      });
      setCreatedStudent(student);
      setStep(2);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFormError(
        typeof detail === "string"
          ? detail
          : "Could not register student. Check if the code is unique."
      );
    } finally {
      setFormLoading(false);
    }
  };

  // ── Step 2: Webcam capture ───────────────────────────────────────────────

  /** Open the webcam modal to start capturing */
  const handleStartCapture = () => {
    setCaptureError("");
    setWebcamOpen(true);
  };

  /** Called by the modal when 30 samples are saved */
  const handleCaptureComplete = () => {
    setWebcamOpen(false);
    setStep(3);
  };

  /** Called by the modal when the user clicks Cancel */
  const handleCaptureCancel = () => {
    setWebcamOpen(false);
  };

  /** Skip face capture for now */
  const handleSkip = () => setStep(3);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {/* Webcam modal (mounted on top of everything) */}
      {webcamOpen && createdStudent && (
        <WebcamCaptureModal
          studentId={createdStudent.id}
          studentName={createdStudent.name}
          onComplete={handleCaptureComplete}
          onCancel={handleCaptureCancel}
        />
      )}

      {/* Header */}
      <div>
        <button
          onClick={() => navigate("/students")}
          className="mb-4 flex items-center gap-1.5 text-xs text-slate-500 transition hover:text-slate-300"
        >
          ← Back to Students
        </button>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Register Student
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Add a new student to the attendance system.
        </p>
      </div>

      {/* Steps */}
      <Steps current={step} />

      {/* ── Step 1: Student details ───────────────────────────────────── */}
      {step === 1 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <h2 className="mb-5 text-sm font-semibold text-slate-200">
            Student Details
          </h2>
          <StudentForm
            mode="create"
            loading={formLoading}
            error={formError}
            onSubmit={handleCreate}
            onCancel={() => navigate("/students")}
          />
        </div>
      )}

      {/* ── Step 2: Face capture ──────────────────────────────────────── */}
      {step === 2 && createdStudent && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg space-y-5">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">
              Capture Face Samples
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              The webcam will automatically capture 30 face samples for{" "}
              <span className="font-medium text-slate-300">
                {createdStudent.name}
              </span>
              . Frames without a visible face are skipped.
            </p>
          </div>

          {captureError && (
            <div className="rounded-xl border border-rose-800/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-400">
              {captureError}
            </div>
          )}

          {/* Capture prompt card */}
          <div className="flex flex-col items-center gap-5 rounded-xl border border-slate-700/60 bg-slate-800/40 py-10 px-6 text-center">
            {/* Animated camera icon */}
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-indigo-600/10 ring-2 ring-indigo-600/20">
              <WebcamIcon className="h-9 w-9 text-indigo-400" />
              {/* Pulse ring */}
              <span className="absolute inset-0 animate-ping rounded-full bg-indigo-500/10" />
            </div>

            <div className="space-y-1">
              <p className="text-sm font-semibold text-slate-200">
                Ready to capture 30 face samples
              </p>
              <p className="text-xs text-slate-500 max-w-xs mx-auto">
                Sit in good lighting, face the camera, and move slightly between
                captures for varied angles — this improves recognition accuracy.
              </p>
            </div>

            {/* Tips */}
            <div className="grid grid-cols-3 gap-3 w-full max-w-sm text-center">
              {[
                { icon: "☀️", tip: "Good lighting" },
                { icon: "👁️", tip: "Face centred" },
                { icon: "🔄", tip: "Vary angles" },
              ].map(({ icon, tip }) => (
                <div
                  key={tip}
                  className="rounded-lg bg-slate-800 px-2 py-2.5 text-xs text-slate-400"
                >
                  <div className="text-lg mb-1">{icon}</div>
                  {tip}
                </div>
              ))}
            </div>

            <button
              onClick={handleStartCapture}
              className="flex items-center gap-2.5 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-900/40 hover:bg-indigo-500 transition"
            >
              <WebcamIcon className="h-4 w-4" />
              Open Camera &amp; Capture
            </button>
          </div>

          <div className="flex justify-start">
            <button
              onClick={handleSkip}
              className="rounded-xl px-5 py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 hover:bg-slate-800 transition"
            >
              Skip for now
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Done ─────────────────────────────────────────────── */}
      {step === 3 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center shadow-lg">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15">
            <svg
              className="h-8 w-8 text-emerald-400"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-white">
            {createdStudent?.name} registered!
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            The student has been added to the system. Face samples can be
            recaptured at any time from the student detail page.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              onClick={() => navigate("/students")}
              className="rounded-xl px-5 py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 hover:bg-slate-800 transition"
            >
              Back to Students
            </button>
            <button
              onClick={() => {
                setStep(1);
                setCreatedStudent(null);
                setFormError(null);
                setCaptureError("");
              }}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
            >
              Register Another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
