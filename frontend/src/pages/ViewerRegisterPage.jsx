import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authService } from "../services/authService";
import { studentService } from "../services/studentService";

/**
 * ViewerRegisterPage
 * ──────────────────
 * Three-step viewer self-registration flow:
 *   Step 1 — Account details form.
 *   Step 2 — 30-sample face capture (rAF loop → single batch POST).
 *   Step 3 — Success screen → redirect to /viewer.
 *
 * Face capture architecture (mirrors desktop + WebcamCaptureModal):
 *   • requestAnimationFrame loop at camera native fps (~30 fps).
 *   • Browser pixel-variance check for real-time face detection UI.
 *   • Desktop-style corner-bracket rectangle drawn on canvas overlay.
 *   • Samples accumulated locally in framesBuffer[].
 *   • ONE batch POST to /students/{id}/capture/batch after 30 frames.
 *   • Total time: ~3 s capture + 1–3 s upload  (was 30–120 s per frame).
 */

// ── Constants ─────────────────────────────────────────────────────────────────
const TOTAL_SAMPLES      = 30;
const SAMPLE_INTERVAL_MS = 100;   // 10 fps sample rate
const JPEG_QUALITY       = 0.82;
const FACE_VARIANCE_MIN  = 18;    // pixel std-dev threshold for "face present"
const FACE_SAMPLE_SIZE   = 80;    // centre-crop px for variance check

// ── Helpers: browser-side face presence ──────────────────────────────────────
function hasFacePresence(ctx, w, h) {
  const x = Math.floor((w - FACE_SAMPLE_SIZE) / 2);
  const y = Math.floor((h - FACE_SAMPLE_SIZE) / 2);
  try {
    const { data } = ctx.getImageData(x, y, FACE_SAMPLE_SIZE, FACE_SAMPLE_SIZE);
    let sum = 0, sumSq = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      const lum = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8;
      sum   += lum;
      sumSq += lum * lum;
    }
    const mean = sum / n;
    return Math.sqrt(sumSq / n - mean * mean) >= FACE_VARIANCE_MIN;
  } catch {
    return false;
  }
}

// ── Helper: desktop-style corner-bracket rectangle ───────────────────────────
function drawFaceRect(ctx, w, h, detected, animPhase) {
  ctx.clearRect(0, 0, w, h);
  const size   = Math.round(Math.min(w, h) * 0.55);
  const rx     = Math.round((w - size) / 2);
  const ry     = Math.round((h - size) / 2);
  const corner = Math.round(size * 0.12);
  const alpha  = detected ? 0.65 + 0.35 * Math.abs(Math.sin(animPhase * Math.PI)) : 0.30;
  const color  = detected ? `rgba(52,211,153,${alpha})` : `rgba(248,113,113,${alpha})`;

  ctx.strokeStyle = color;
  ctx.lineWidth   = 2.5;
  ctx.lineCap     = "round";

  [
    [[rx,            ry + corner], [rx,            ry           ], [rx + corner,      ry           ]],
    [[rx+size-corner,ry          ], [rx + size,     ry           ], [rx + size,        ry + corner  ]],
    [[rx,            ry+size-corner],[rx,           ry + size    ], [rx + corner,      ry + size    ]],
    [[rx+size-corner,ry+size     ], [rx + size,     ry + size    ], [rx + size,        ry+size-corner]],
  ].forEach(([start, mid, end]) => {
    ctx.beginPath();
    ctx.moveTo(...start);
    ctx.lineTo(...mid);
    ctx.lineTo(...end);
    ctx.stroke();
  });
}

// ── Helper: extract readable message from FastAPI error responses ─────────────
// FastAPI returns either:
//   { detail: "string message" }           — HTTPException
//   { detail: [{ msg, loc, ... }, ...] }   — RequestValidationError
function extractApiError(err) {
  const detail = err?.response?.data?.detail;
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg ?? String(d)).join(" | ");
  }
  return String(detail);
}

// ── Shared sub-components (module-scope to avoid remount on re-render) ────────

function ToggleBtn({ show, onToggle }) {
  return (
    <button
      type="button"
      tabIndex={-1}
      onClick={onToggle}
      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
    >
      {show ? (
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      )}
    </button>
  );
}

function Field({ label, name, type = "text", placeholder, error, suffix, form, onChange }) {
  return (
    <div className="space-y-1">
      <label htmlFor={name} className="block text-sm font-medium text-slate-300">{label}</label>
      <div className="relative">
        <input
          id={name} name={name} type={type}
          autoComplete={name}
          value={form[name]}
          onChange={onChange}
          placeholder={placeholder}
          className={[
            "block w-full rounded-xl border bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:outline-none focus:ring-1",
            error ? "border-rose-600 focus:border-rose-500 focus:ring-rose-500"
                  : "border-slate-700 focus:border-indigo-500 focus:ring-indigo-500",
            suffix ? "pr-10" : "",
          ].join(" ")}
        />
        {suffix}
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepIndicator({ current }) {
  const steps = ["Account Details", "Face Capture", "Complete"];
  return (
    <div className="mb-8 flex items-center justify-center gap-2">
      {steps.map((label, i) => {
        const idx    = i + 1;
        const done   = current > idx;
        const active = current === idx;
        return (
          <div key={label} className="flex items-center gap-2">
            <div className="flex flex-col items-center gap-1">
              <div className={[
                "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all",
                done   ? "bg-emerald-600 text-white"
                : active ? "bg-indigo-600 text-white ring-4 ring-indigo-600/30"
                         : "bg-slate-800 text-slate-500",
              ].join(" ")}>
                {done ? (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={3} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : idx}
              </div>
              <span className={[
                "text-xs",
                active ? "text-indigo-400" : done ? "text-emerald-500" : "text-slate-600",
              ].join(" ")}>{label}</span>
            </div>
            {i < steps.length - 1 && (
              <div className={["mb-4 h-px w-12", done ? "bg-emerald-600" : "bg-slate-700"].join(" ")} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Step 1 — Account Details ──────────────────────────────────────────────────

function AccountDetailsStep({ onSuccess }) {
  const [form, setForm]         = useState({
    full_name: "", student_code: "", email: "",
    username: "", password: "", confirm_password: "", department: "",
  });
  const [errors,   setErrors]   = useState({});
  const [apiError, setApiError] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [showPw,   setShowPw]   = useState(false);
  const [showCpw,  setShowCpw]  = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));
    if (errors[name]) setErrors((p) => ({ ...p, [name]: "" }));
    if (apiError) setApiError("");
  };

  const validate = () => {
    const errs = {};
    if (!form.full_name.trim())        errs.full_name        = "Full name is required.";
    if (!form.student_code.trim())     errs.student_code     = "Student code is required.";
    if (!form.email.trim())            errs.email            = "Email is required.";
    else if (!/\S+@\S+\.\S+/.test(form.email)) errs.email   = "Enter a valid email.";
    if (!form.username.trim())         errs.username         = "Username is required.";
    else if (form.username.length < 3) errs.username         = "Username must be at least 3 characters.";
    if (!form.password)                errs.password         = "Password is required.";
    else if (form.password.length < 6) errs.password         = "Password must be at least 6 characters.";
    if (!form.confirm_password)        errs.confirm_password = "Please confirm your password.";
    else if (form.password !== form.confirm_password)
      errs.confirm_password = "Passwords do not match.";
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setApiError("");
    setLoading(true);
    try {
      const result = await authService.registerViewer({
        full_name:        form.full_name.trim(),
        student_code:     form.student_code.trim(),
        email:            form.email.trim(),
        username:         form.username.trim(),
        password:         form.password,
        confirm_password: form.confirm_password,
        department:       form.department.trim() || undefined,
      });
      onSuccess(result);
    } catch (err) {
      // Surface the real backend message (500 detail, 422 validation array, etc.)
      const msg = extractApiError(err);
      setApiError(msg || "Registration failed. Please check your details and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <Field label="Full Name"    name="full_name"    placeholder="Alice Smith"             error={errors.full_name}    form={form} onChange={handleChange} />
      <Field label="Student Code" name="student_code" placeholder="CS-2024-001"             error={errors.student_code} form={form} onChange={handleChange} />
      <Field label="Email"        name="email"        type="email" placeholder="alice@example.com" error={errors.email} form={form} onChange={handleChange} />
      <Field label="Username"     name="username"     placeholder="alice_smith"              error={errors.username}     form={form} onChange={handleChange} />
      <Field label="Department"   name="department"   placeholder="Computer Science (optional)" error={errors.department} form={form} onChange={handleChange} />

      {/* Password */}
      <div className="space-y-1">
        <label htmlFor="password" className="block text-sm font-medium text-slate-300">Password</label>
        <div className="relative">
          <input
            id="password" name="password"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            value={form.password}
            onChange={handleChange}
            placeholder="••••••••"
            className={[
              "block w-full rounded-xl border bg-slate-800 px-4 py-2.5 pr-10 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:outline-none focus:ring-1",
              errors.password ? "border-rose-600 focus:border-rose-500 focus:ring-rose-500"
                              : "border-slate-700 focus:border-indigo-500 focus:ring-indigo-500",
            ].join(" ")}
          />
          <ToggleBtn show={showPw} onToggle={() => setShowPw((v) => !v)} />
        </div>
        {errors.password && <p className="text-xs text-rose-400">{errors.password}</p>}
      </div>

      {/* Confirm Password */}
      <div className="space-y-1">
        <label htmlFor="confirm_password" className="block text-sm font-medium text-slate-300">Confirm Password</label>
        <div className="relative">
          <input
            id="confirm_password" name="confirm_password"
            type={showCpw ? "text" : "password"}
            autoComplete="new-password"
            value={form.confirm_password}
            onChange={handleChange}
            placeholder="••••••••"
            className={[
              "block w-full rounded-xl border bg-slate-800 px-4 py-2.5 pr-10 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:outline-none focus:ring-1",
              errors.confirm_password ? "border-rose-600 focus:border-rose-500 focus:ring-rose-500"
                                      : "border-slate-700 focus:border-indigo-500 focus:ring-indigo-500",
            ].join(" ")}
          />
          <ToggleBtn show={showCpw} onToggle={() => setShowCpw((v) => !v)} />
        </div>
        {errors.confirm_password && <p className="text-xs text-rose-400">{errors.confirm_password}</p>}
      </div>

      {/* API error box — shows the real backend message */}
      {apiError && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          <svg className="mt-0.5 h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <span>{apiError}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-700/30 transition-all hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />}
        {loading ? "Creating account…" : "Continue to Face Capture"}
      </button>
    </form>
  );
}

// ── Step 2 — Face Capture ─────────────────────────────────────────────────────
//
// Mirrors the desktop app and WebcamCaptureModal (admin flow) exactly:
//   • rAF loop at native camera fps → draws face rectangle on overlay canvas.
//   • Pixel-variance check for instant (zero-RTT) face-detected feedback.
//   • Blobs buffered locally in framesBuffer[].
//   • Single captureFaceBatch() call when buffer reaches TOTAL_SAMPLES.
//   • "Uploading…" progress overlay shown during the one network call.

function FaceCaptureStep({ studentId, onComplete }) {
  const videoRef      = useRef(null);
  const captureCanvas = useRef(null);   // hidden — raw (unmirrored) pixel grab
  const overlayCanvas = useRef(null);   // visible — face rect drawn here
  const streamRef     = useRef(null);
  const rafRef        = useRef(null);
  const lastSampleRef = useRef(0);
  const framesBuffer  = useRef([]);
  const animPhaseRef  = useRef(0);

  // phase: "init" | "ready" | "capturing" | "uploading" | "done" | "error"
  const [phase,          setPhase]          = useState("init");
  const [sampleCount,    setSampleCount]    = useState(0);
  const [faceDetected,   setFaceDetected]   = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMsg,       setErrorMsg]       = useState("");

  // ── Stop everything ────────────────────────────────────────────────────────
  const stopAll = useCallback(() => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
  }, []);

  // ── Camera init ────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        if (!cancelled) setPhase("ready");
      } catch (err) {
        if (!cancelled) {
          setErrorMsg(
            err.name === "NotAllowedError" || err.name === "PermissionDeniedError"
              ? "Camera access denied. Please allow camera access and refresh."
              : `Camera error: ${err.message}`,
          );
          setPhase("error");
        }
      }
    })();
    return () => { cancelled = true; stopAll(); };
  }, [stopAll]);

  // ── Batch upload — ONE call after all 30 frames collected ──────────────────
  const uploadBatch = useCallback(async (blobs) => {
    setPhase("uploading");
    setUploadProgress(0);
    try {
      const ticker = setInterval(() => setUploadProgress((p) => Math.min(p + 6, 88)), 120);
      await studentService.captureFaceBatch(studentId, blobs);
      clearInterval(ticker);
      setUploadProgress(100);
      setPhase("done");
    } catch (err) {
      setPhase("error");
      setErrorMsg(extractApiError(err) ?? "Upload failed. Please try again.");
    }
  }, [studentId]);

  // ── rAF capture loop ───────────────────────────────────────────────────────
  const runCaptureLoop = useCallback(() => {
    const video   = videoRef.current;
    const canvas  = captureCanvas.current;
    const overlay = overlayCanvas.current;
    if (!video || !canvas || !overlay || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(runCaptureLoop);
      return;
    }

    const vw = video.videoWidth  || 640;
    const vh = video.videoHeight || 480;
    if (canvas.width  !== vw) canvas.width  = vw;
    if (canvas.height !== vh) canvas.height = vh;

    const rect = overlay.getBoundingClientRect();
    const rw   = Math.round(rect.width);
    const rh   = Math.round(rect.height);
    if (overlay.width  !== rw) overlay.width  = rw;
    if (overlay.height !== rh) overlay.height = rh;

    // Draw frame into hidden canvas
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, vw, vh);

    // Browser-side face presence (no server call)
    const facePresent = hasFacePresence(ctx, vw, vh);
    setFaceDetected(facePresent);

    // Animate phase for pulsing rectangle
    animPhaseRef.current = (animPhaseRef.current + 0.05) % 2;

    // Draw desktop-style corner-bracket rectangle on overlay
    const oCtx = overlay.getContext("2d");
    drawFaceRect(oCtx, rw, rh, facePresent, animPhaseRef.current);

    // "Samples: X / 30" counter inside the box
    const count   = framesBuffer.current.length;
    const boxSize = Math.round(Math.min(rw, rh) * 0.55);
    const boxX    = Math.round((rw - boxSize) / 2);
    const boxY    = Math.round((rh - boxSize) / 2);
    oCtx.font      = "bold 13px monospace";
    oCtx.textAlign = "center";
    oCtx.fillStyle = facePresent ? "rgba(52,211,153,0.95)" : "rgba(248,113,113,0.70)";
    oCtx.fillText(`Samples: ${count} / ${TOTAL_SAMPLES}`, boxX + boxSize / 2, boxY + 24);

    // Collect one blob every SAMPLE_INTERVAL_MS when face is present
    const now = performance.now();
    if (facePresent && framesBuffer.current.length < TOTAL_SAMPLES && now - lastSampleRef.current >= SAMPLE_INTERVAL_MS) {
      lastSampleRef.current = now;
      canvas.toBlob((blob) => {
        if (!blob || framesBuffer.current.length >= TOTAL_SAMPLES) return;
        framesBuffer.current.push(blob);
        const newCount = framesBuffer.current.length;
        setSampleCount(newCount);
        if (newCount >= TOTAL_SAMPLES) {
          if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
          stopAll();
          uploadBatch([...framesBuffer.current]);
        }
      }, "image/jpeg", JPEG_QUALITY);
    }

    if (framesBuffer.current.length < TOTAL_SAMPLES) {
      rafRef.current = requestAnimationFrame(runCaptureLoop);
    }
  }, [stopAll, uploadBatch]);

  // ── Start loop when user clicks "Start" ───────────────────────────────────
  const startCapture = useCallback(() => {
    framesBuffer.current  = [];
    lastSampleRef.current = 0;
    setSampleCount(0);
    setFaceDetected(false);
    setPhase("capturing");
  }, []);

  useEffect(() => {
    if (phase !== "capturing") return;
    rafRef.current = requestAnimationFrame(runCaptureLoop);
    return () => { if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; } };
  }, [phase, runCaptureLoop]);

  // ── Retry ─────────────────────────────────────────────────────────────────
  const handleRetry = useCallback(() => {
    framesBuffer.current = [];
    setSampleCount(0);
    setFaceDetected(false);
    setUploadProgress(0);
    setErrorMsg("");
    stopAll();
    // Re-init camera
    setPhase("init");
    navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    }).then((stream) => {
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); }
      setPhase("ready");
    }).catch((err) => {
      setErrorMsg(`Camera error: ${err.message}`);
      setPhase("error");
    });
  }, [stopAll]);

  // ── Redirect on done ──────────────────────────────────────────────────────
  useEffect(() => {
    if (phase !== "done") return;
    const t = setTimeout(onComplete, 1500);
    return () => clearTimeout(t);
  }, [phase, onComplete]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const isInit      = phase === "init";
  const isReady     = phase === "ready";
  const isCapturing = phase === "capturing";
  const isUploading = phase === "uploading";
  const isDone      = phase === "done";
  const isError     = phase === "error";
  const progress    = Math.min((sampleCount / TOTAL_SAMPLES) * 100, 100);

  return (
    <div className="space-y-4">
      <p className="text-center text-sm text-slate-400">
        Position your face clearly in the camera. We&apos;ll capture {TOTAL_SAMPLES} samples automatically.
      </p>

      {/* ── Video + overlay ─────────────────────────────────────────────── */}
      <div
        className="relative overflow-hidden rounded-xl border border-slate-700 bg-black"
        style={{ aspectRatio: "4/3" }}
      >
        {/* Mirrored video — selfie feel */}
        <video
          ref={videoRef}
          muted
          playsInline
          className={`h-full w-full object-cover transition-opacity duration-500 ${
            isCapturing || isDone ? "opacity-100" : "opacity-60"
          }`}
          style={{ transform: "scaleX(-1)" }}
        />

        {/* Hidden capture canvas — NOT mirrored, raw pixels sent to server */}
        <canvas ref={captureCanvas} className="hidden" />

        {/* Overlay canvas — mirrored to match video so rect appears correctly */}
        <canvas
          ref={overlayCanvas}
          className={`pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-300 ${
            isCapturing ? "opacity-100" : "opacity-0"
          }`}
          style={{ transform: "scaleX(-1)" }}
        />

        {/* Camera initialising spinner */}
        {isInit && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            <p className="text-xs text-slate-400">Starting camera…</p>
          </div>
        )}

        {/* Uploading overlay — shown while the single batch POST is in flight */}
        {isUploading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-950/90">
            <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-indigo-500 border-t-transparent" />
            <div className="w-52 space-y-2 text-center">
              <p className="text-sm font-semibold text-slate-200">Uploading samples…</p>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all duration-200"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-xs text-slate-500">{uploadProgress}%</p>
            </div>
          </div>
        )}

        {/* Done overlay */}
        {isDone && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-emerald-950/90">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/20 ring-2 ring-emerald-500/50">
              <svg className="h-7 w-7 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold text-emerald-300">Face registration complete</p>
              <p className="mt-0.5 text-xs text-emerald-500">{TOTAL_SAMPLES} samples captured successfully</p>
            </div>
          </div>
        )}

        {/* Face detected / not detected badge (top-right, visible while capturing) */}
        {isCapturing && (
          <div className={[
            "absolute right-3 top-3 flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium backdrop-blur-sm",
            faceDetected ? "bg-emerald-900/80 text-emerald-300" : "bg-rose-900/80 text-rose-300",
          ].join(" ")}>
            <span className={[
              "h-2 w-2 rounded-full",
              faceDetected ? "bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.5)]" : "bg-rose-400",
            ].join(" ")} />
            {faceDetected ? "Face detected" : "No face detected"}
          </div>
        )}
      </div>

      {/* ── Status row (face indicator + sample counter) ─────────────────── */}
      {isCapturing && (
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            <span className={[
              "h-2 w-2 rounded-full transition-all duration-200",
              faceDetected ? "bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.5)]" : "bg-rose-500",
            ].join(" ")} />
            <span className={faceDetected ? "text-emerald-400" : "text-rose-400"}>
              {faceDetected ? "Face detected — hold still" : "No face detected"}
            </span>
          </div>
          <span className="font-mono font-semibold tabular-nums text-slate-300">
            {sampleCount} / {TOTAL_SAMPLES}
          </span>
        </div>
      )}

      {/* ── Progress bar ─────────────────────────────────────────────────── */}
      {(isCapturing || isDone) && (
        <div className="space-y-1">
          <div className="mb-1 flex justify-between text-xs text-slate-400">
            <span>{isDone ? "Complete!" : "Collecting samples…"}</span>
            <span>{sampleCount} / {TOTAL_SAMPLES}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full transition-all duration-150"
              style={{
                width: `${progress}%`,
                background: isDone
                  ? "#10b981"
                  : "linear-gradient(90deg,#6366f1 0%,#818cf8 100%)",
              }}
            />
          </div>
          {isCapturing && (
            <p className="text-[11px] text-slate-500">
              Keep your face centred and try different angles for better accuracy.
            </p>
          )}
        </div>
      )}

      {/* ── Error box ────────────────────────────────────────────────────── */}
      {isError && (
        <div className="space-y-3 rounded-xl border border-rose-800/40 bg-rose-950/40 p-4">
          <div className="flex items-start gap-3">
            <svg className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <p className="text-sm text-rose-400">{errorMsg}</p>
          </div>
          <button
            onClick={handleRetry}
            className="w-full rounded-lg bg-rose-900/50 py-2 text-xs font-semibold text-rose-300 transition hover:bg-rose-900/80"
          >
            Try Again
          </button>
        </div>
      )}

      {/* ── Start button ─────────────────────────────────────────────────── */}
      {isReady && (
        <button
          onClick={startCapture}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-700/30 transition-all hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900"
        >
          Start Face Capture
        </button>
      )}

      {/* ── Capturing spinner + hint ─────────────────────────────────────── */}
      {isCapturing && (
        <div className="flex items-center justify-center gap-2 py-0.5 text-sm text-indigo-400">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          Capturing… please hold still
        </div>
      )}

      {/* ── Footer hint during upload ────────────────────────────────────── */}
      {isUploading && (
        <p className="text-center text-xs text-slate-500">
          Sending {TOTAL_SAMPLES} frames to server…
        </p>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ViewerRegisterPage() {
  const navigate = useNavigate();

  const [step,      setStep]      = useState(1);
  const [regResult, setRegResult] = useState(null);

  const handleStep1Success = (result) => {
    setRegResult(result);
    setStep(2);
  };

  const handleFaceCaptureComplete = () => {
    setStep(3);
    setTimeout(() => navigate("/viewer", { replace: true }), 1500);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12">
      {/* Background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-1/3 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-700/10 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Header */}
        <div className="mb-6 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-700/40">
            <svg className="h-7 w-7 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold tracking-tight text-white">Create Viewer Account</h1>
            <p className="text-sm text-slate-500">Smart Attendance System</p>
          </div>
        </div>

        <StepIndicator current={step} />

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
          {step === 1 && <AccountDetailsStep onSuccess={handleStep1Success} />}

          {step === 2 && regResult && (
            <FaceCaptureStep
              studentId={regResult.student_id}
              onComplete={handleFaceCaptureComplete}
            />
          )}

          {step === 3 && (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-600/20 ring-4 ring-emerald-600/20">
                <svg className="h-8 w-8 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="text-lg font-semibold text-white">Registration complete!</p>
                <p className="mt-1 text-sm text-slate-400">Redirecting to your dashboard…</p>
              </div>
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            </div>
          )}
        </div>

        {step === 1 && (
          <p className="mt-5 text-center text-sm text-slate-400">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-indigo-400 underline-offset-2 hover:text-indigo-300 hover:underline">
              Sign in
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
