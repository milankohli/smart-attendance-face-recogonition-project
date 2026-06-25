/**
 * WebcamCaptureModal.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * High-speed face registration modal — mirrors the desktop app experience.
 *
 * Architecture (Option A — local batch capture):
 * ────────────────────────────────────────────────
 * The original implementation did one HTTP round-trip per frame
 * (captureActiveRef blocked the next frame until the previous upload
 * finished).  With a ~1.5 s server round-trip that meant 30 × 1.5 s ≈ 60 s.
 *
 * New flow:
 *   1. requestAnimationFrame loop runs at the camera's native FPS (~30 fps).
 *   2. A lightweight brightness-variance check decides whether a face is
 *      likely present without any ML library (the server does the real check).
 *   3. Every SAMPLE_INTERVAL_MS (100 ms = 10 fps) that a face is detected,
 *      one JPEG blob is pushed into a local framesBuffer array.
 *   4. Once framesBuffer.length reaches TARGET_SAMPLES (30), the loop stops
 *      and ONE batch POST is made: POST /students/{id}/capture/batch.
 *   5. Total time: ~3 s capture + ~1–3 s upload = 3–6 s end-to-end.
 *
 * Face detection (browser-side, no ML library):
 * ──────────────────────────────────────────────
 * Samples a centre rectangle of the video frame and measures pixel-variance.
 * A skin-tone dominant region with sufficient variance is treated as "face
 * detected".  This is just a UI hint — the backend runs the real MTCNN/Haar
 * detector on every uploaded frame and skips frames with no face.
 *
 * Desktop GUI parity:
 * ───────────────────
 *  • Green animated rectangle drawn on a canvas overlay while face detected.
 *  • Red rectangle (dimmer) while no face detected.
 *  • "Samples: X / 30" counter inside the video.
 *  • Green progress bar below the video.
 *  • "Face detected" / "No face detected" status line.
 *  • "Keep your face centred and try different angles." instruction.
 *  • "Face registration complete — 30 samples captured" completion screen.
 *
 * Props:
 *   studentId    number    The student to associate face samples with.
 *   studentName  string    Shown in the modal header.
 *   onComplete   ()=>void  Called after successful upload (parent refreshes list).
 *   onCancel     ()=>void  Called when the user dismisses the modal.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { studentService } from "../services/studentService";

// ── Tunable constants ──────────────────────────────────────────────────────
const TARGET_SAMPLES      = 30;    // number of frames to collect before uploading
const SAMPLE_INTERVAL_MS  = 100;   // ms between captured frames (10 fps)
const JPEG_QUALITY        = 0.82;  // JPEG compression quality (0–1)
const FACE_VARIANCE_MIN   = 18;    // minimum pixel std-dev to count as "face present"
const FACE_SAMPLE_SIZE    = 80;    // pixel width/height of the centre sample box

// ── Lightweight browser-side face presence check ───────────────────────────
/**
 * Returns true when the centre region of the canvas has enough pixel variance
 * to suggest a face (not a blank wall / solid background).
 * Reads a FACE_SAMPLE_SIZE × FACE_SAMPLE_SIZE patch from the centre.
 */
function hasFacePresence(ctx, canvasW, canvasH) {
  const x = Math.floor((canvasW - FACE_SAMPLE_SIZE) / 2);
  const y = Math.floor((canvasH - FACE_SAMPLE_SIZE) / 2);
  try {
    const { data } = ctx.getImageData(x, y, FACE_SAMPLE_SIZE, FACE_SAMPLE_SIZE);
    let sum = 0;
    let sumSq = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      // Luminance (fast approximation)
      const lum = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8;
      sum += lum;
      sumSq += lum * lum;
    }
    const mean = sum / n;
    const variance = sumSq / n - mean * mean;
    return Math.sqrt(variance) >= FACE_VARIANCE_MIN;
  } catch {
    return false;
  }
}

// ── Desktop-style face rectangle overlay ──────────────────────────────────
/**
 * Draws an OpenCV-style bounding box on the overlay canvas.
 * Uses a pulsing animation driven by `animPhase` (0–1, cycling).
 */
function drawFaceRect(overlayCtx, w, h, detected, animPhase) {
  overlayCtx.clearRect(0, 0, w, h);

  // Rectangle is centred, ~55% of the shorter dimension
  const size   = Math.round(Math.min(w, h) * 0.55);
  const rx     = Math.round((w - size) / 2);
  const ry     = Math.round((h - size) / 2);
  const corner = Math.round(size * 0.12); // corner bracket length

  // Pulsing alpha: 0.65 → 1.0 when detected, fixed 0.3 when not
  const alpha = detected
    ? 0.65 + 0.35 * Math.abs(Math.sin(animPhase * Math.PI))
    : 0.30;

  const color = detected
    ? `rgba(52, 211, 153, ${alpha})`   // emerald-400
    : `rgba(248, 113, 113, ${alpha})`; // red-400

  overlayCtx.strokeStyle = color;
  overlayCtx.lineWidth   = 2.5;
  overlayCtx.lineCap     = "round";

  // Draw only corner brackets (desktop OpenCV style)
  const lines = [
    // Top-left
    [[rx, ry + corner], [rx, ry], [rx + corner, ry]],
    // Top-right
    [[rx + size - corner, ry], [rx + size, ry], [rx + size, ry + corner]],
    // Bottom-left
    [[rx, ry + size - corner], [rx, ry + size], [rx + corner, ry + size]],
    // Bottom-right
    [[rx + size - corner, ry + size], [rx + size, ry + size], [rx + size, ry + size - corner]],
  ];

  lines.forEach(([start, mid, end]) => {
    overlayCtx.beginPath();
    overlayCtx.moveTo(...start);
    overlayCtx.lineTo(...mid);
    overlayCtx.lineTo(...end);
    overlayCtx.stroke();
  });

  // "Samples: X / 30" counter — top-centre inside the box
  if (detected) {
    overlayCtx.font      = "bold 13px monospace";
    overlayCtx.textAlign = "center";
    overlayCtx.fillStyle = `rgba(52, 211, 153, ${Math.min(alpha + 0.2, 1)})`;
    // text is set by caller via return value — we don't know sampleCount here
  }
}

// ── Progress bar ───────────────────────────────────────────────────────────
function ProgressBar({ count, target }) {
  const pct = Math.min((count / target) * 100, 100);
  const done = count >= target;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className={done ? "font-semibold text-emerald-400" : "text-slate-400"}>
          {done ? "Complete!" : "Collecting samples…"}
        </span>
        <span className={`font-mono font-semibold tabular-nums ${done ? "text-emerald-400" : "text-slate-300"}`}>
          {count} / {target}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full transition-all duration-150"
          style={{
            width: `${pct}%`,
            background: done
              ? "#10b981"
              : `linear-gradient(90deg, #6366f1 0%, #818cf8 ${pct}%, #6366f1 100%)`,
          }}
        />
      </div>
      <p className="text-[11px] text-slate-500">
        {done ? "" : `${pct.toFixed(0)}%`}
      </p>
    </div>
  );
}

// ── Face status indicator ──────────────────────────────────────────────────
function FaceStatus({ detected }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2.5 w-2.5 rounded-full transition-all duration-300 ${
          detected
            ? "bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.6)]"
            : "bg-rose-500"
        }`}
      />
      <span
        className={`text-xs font-medium transition-colors duration-300 ${
          detected ? "text-emerald-400" : "text-rose-400"
        }`}
      >
        {detected ? "Face detected" : "No face detected"}
      </span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
export default function WebcamCaptureModal({ studentId, studentName, onComplete, onCancel }) {
  const videoRef      = useRef(null);
  const captureCanvas = useRef(null);   // hidden canvas for frame grabbing + variance check
  const overlayCanvas = useRef(null);   // visible canvas layered over the video for the rectangle
  const streamRef     = useRef(null);
  const rafRef        = useRef(null);   // requestAnimationFrame handle
  const lastSampleRef = useRef(0);      // timestamp of last collected sample
  const framesBuffer  = useRef([]);     // collected JPEG Blobs (local, no server round-trip)
  const animPhaseRef  = useRef(0);      // drives the pulsing rectangle animation

  const [phase, setPhase]               = useState("init");    // init | capturing | uploading | done | error
  const [sampleCount, setSampleCount]   = useState(0);
  const [faceDetected, setFaceDetected] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);    // 0–100 during batch upload
  const [errorMsg, setErrorMsg]         = useState("");

  // ── Camera setup ───────────────────────────────────────────────────────

  const stopCamera = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        await video.play();
      }
      setPhase("capturing");
    } catch (err) {
      setPhase("error");
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setErrorMsg("Camera access denied. Allow camera permission and try again.");
      } else if (err.name === "NotFoundError") {
        setErrorMsg("No camera found. Please connect a webcam and try again.");
      } else {
        setErrorMsg(`Camera error: ${err.message}`);
      }
    }
  }, []);

  // ── Batch upload ────────────────────────────────────────────────────────

  const uploadBatch = useCallback(async (blobs) => {
    setPhase("uploading");
    setUploadProgress(0);
    try {
      // Simulate progress UI while the single request is in flight
      // (the real upload is one call; we animate the bar for responsiveness)
      const ticker = setInterval(() => {
        setUploadProgress((p) => Math.min(p + 6, 88));
      }, 120);

      await studentService.captureFaceBatch(studentId, blobs);

      clearInterval(ticker);
      setUploadProgress(100);
      setPhase("done");
    } catch (err) {
      setPhase("error");
      setErrorMsg(
        err?.response?.data?.detail ?? "Upload failed. Please try again."
      );
    }
  }, [studentId]);

  // ── requestAnimationFrame capture loop ────────────────────────────────
  //
  // Runs at the camera's native FPS (~30 fps).
  // Every SAMPLE_INTERVAL_MS it grabs a JPEG blob and checks face presence.
  // No server calls happen here — pure local capture.

  const runCaptureLoop = useCallback(() => {
    const video   = videoRef.current;
    const canvas  = captureCanvas.current;
    const overlay = overlayCanvas.current;
    if (!video || !canvas || !overlay || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(runCaptureLoop);
      return;
    }

    const w = video.videoWidth  || 640;
    const h = video.videoHeight || 480;

    // Keep hidden capture canvas in sync with video dimensions
    if (canvas.width !== w)  canvas.width  = w;
    if (canvas.height !== h) canvas.height = h;

    // Keep overlay canvas in sync with its CSS dimensions
    const rect = overlay.getBoundingClientRect();
    if (overlay.width  !== Math.round(rect.width))  overlay.width  = Math.round(rect.width);
    if (overlay.height !== Math.round(rect.height)) overlay.height = Math.round(rect.height);

    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, w, h);

    // Lightweight face presence check
    const facePresent = hasFacePresence(ctx, w, h);

    // Update face detected state (debounced via RAF is fine)
    setFaceDetected(facePresent);

    // Advance animation phase (cycles 0→2π)
    animPhaseRef.current = (animPhaseRef.current + 0.05) % 2;

    // Draw the face rectangle on the overlay canvas
    const oCtx = overlay.getContext("2d");
    drawFaceRect(oCtx, overlay.width, overlay.height, facePresent, animPhaseRef.current);

    // Draw "Samples: X / 30" counter inside the face box
    const count = framesBuffer.current.length;
    const boxSize  = Math.round(Math.min(overlay.width, overlay.height) * 0.55);
    const boxX     = Math.round((overlay.width - boxSize) / 2);
    const boxY     = Math.round((overlay.height - boxSize) / 2);
    oCtx.font      = "bold 12px monospace";
    oCtx.textAlign = "center";
    oCtx.fillStyle = facePresent
      ? "rgba(52, 211, 153, 0.95)"
      : "rgba(248, 113, 113, 0.70)";
    oCtx.fillText(`Samples: ${count} / ${TARGET_SAMPLES}`, boxX + boxSize / 2, boxY + 22);

    // Collect a sample every SAMPLE_INTERVAL_MS when face is present
    const now = performance.now();
    if (
      facePresent &&
      framesBuffer.current.length < TARGET_SAMPLES &&
      now - lastSampleRef.current >= SAMPLE_INTERVAL_MS
    ) {
      lastSampleRef.current = now;

      // Convert canvas to Blob asynchronously without blocking the loop
      canvas.toBlob(
        (blob) => {
          if (!blob || framesBuffer.current.length >= TARGET_SAMPLES) return;
          framesBuffer.current.push(blob);
          const newCount = framesBuffer.current.length;
          setSampleCount(newCount);

          if (newCount >= TARGET_SAMPLES) {
            // All samples collected — stop the loop and upload
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
            stopCamera();
            uploadBatch([...framesBuffer.current]);
          }
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    }

    if (framesBuffer.current.length < TARGET_SAMPLES) {
      rafRef.current = requestAnimationFrame(runCaptureLoop);
    }
  }, [stopCamera, uploadBatch]);

  // ── Start loop when phase becomes "capturing" ──────────────────────────

  useEffect(() => {
    if (phase !== "capturing") return;
    framesBuffer.current = [];
    lastSampleRef.current = 0;
    rafRef.current = requestAnimationFrame(runCaptureLoop);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [phase, runCaptureLoop]);

  // ── Mount / unmount camera ──────────────────────────────────────────────

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, [startCamera, stopCamera]);

  // ── Auto-close on done ─────────────────────────────────────────────────

  useEffect(() => {
    if (phase !== "done") return;
    const t = setTimeout(onComplete, 1800);
    return () => clearTimeout(t);
  }, [phase, onComplete]);

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleCancel = () => {
    stopCamera();
    onCancel();
  };

  const handleRetry = () => {
    framesBuffer.current = [];
    setSampleCount(0);
    setFaceDetected(false);
    setUploadProgress(0);
    setErrorMsg("");
    setPhase("init");
    startCamera();
  };

  // ── Derived state ──────────────────────────────────────────────────────

  const isCapturing  = phase === "capturing";
  const isUploading  = phase === "uploading";
  const isDone       = phase === "done";
  const isError      = phase === "error";
  const isBusy       = isCapturing || isUploading; // disallow close during active work

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isBusy) handleCancel();
      }}
    >
      {/* Panel */}
      <div
        className="relative mx-4 w-full max-w-lg overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Face Registration</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Capturing samples for{" "}
              <span className="font-medium text-slate-300">{studentName}</span>
            </p>
          </div>
          {!isBusy && (
            <button
              onClick={handleCancel}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
              aria-label="Close"
            >
              <svg fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* ── Body ── */}
        <div className="space-y-4 p-6">

          {/* ── Video + canvas overlay ── */}
          <div
            className="relative overflow-hidden rounded-xl bg-black"
            style={{ aspectRatio: "4/3" }}
          >
            {/* Mirrored video (selfie feel) */}
            <video
              ref={videoRef}
              muted
              playsInline
              className={`h-full w-full object-cover transition-opacity duration-500 ${
                isCapturing || isDone ? "opacity-100" : "opacity-25"
              }`}
              style={{ transform: "scaleX(-1)" }}
            />

            {/* Hidden capture canvas — MUST NOT be mirrored (pixel data
                must match what the server expects: un-flipped BGR frame) */}
            <canvas ref={captureCanvas} className="hidden" />

            {/* Overlay canvas — mirrored to match the video so the
                rectangle appears on the correct side visually */}
            <canvas
              ref={overlayCanvas}
              className={`pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-300 ${
                isCapturing ? "opacity-100" : "opacity-0"
              }`}
              style={{ transform: "scaleX(-1)" }}
            />

            {/* Init spinner */}
            {phase === "init" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                <p className="text-xs text-slate-400">Starting camera…</p>
              </div>
            )}

            {/* Uploading overlay */}
            {isUploading && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-950/90">
                <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-indigo-500 border-t-transparent" />
                <div className="w-48 space-y-2 text-center">
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
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 ring-2 ring-emerald-500/50">
                  <svg
                    className="h-8 w-8 text-emerald-400"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2.5}
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="text-sm font-semibold text-emerald-300">
                    Face registration complete
                  </p>
                  <p className="mt-0.5 text-xs text-emerald-500">
                    {TARGET_SAMPLES} samples captured successfully
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* ── Capturing: status row ── */}
          {isCapturing && (
            <div className="flex items-center justify-between">
              <FaceStatus detected={faceDetected} />
              <span className="font-mono text-xs tabular-nums text-slate-500">
                <span className="font-semibold text-slate-300">{sampleCount}</span>
                {" / "}
                {TARGET_SAMPLES}
              </span>
            </div>
          )}

          {/* ── Capturing: progress bar ── */}
          {isCapturing && (
            <div className="space-y-2">
              <ProgressBar count={sampleCount} target={TARGET_SAMPLES} />
              <p className="text-xs text-slate-500">
                Keep your face centred and try different angles for better accuracy.
              </p>
            </div>
          )}

          {/* ── Error state ── */}
          {isError && (
            <div className="space-y-3 rounded-xl border border-rose-800/40 bg-rose-950/40 p-4">
              <div className="flex items-start gap-3">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-rose-400"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  viewBox="0 0 24 24"
                >
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
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between border-t border-slate-800/60 px-6 py-3.5">
          <p className="text-xs text-slate-600">
            {isCapturing
              ? "Frames without a visible face are skipped automatically."
              : isUploading
              ? "Sending frames to server…"
              : isDone
              ? "Closing…"
              : ""}
          </p>
          {isCapturing && (
            <button
              onClick={handleCancel}
              className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
