/**
 * AttendanceCameraModal.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Desktop-like face recognition modal for marking attendance.
 *
 * Frame flow (mirrors desktop app):
 *   webcam → canvas → attendanceService.identify() → RecognitionResponse
 *
 * Uses attendanceService.identify() (HTTP, per-frame) rather than the passive
 * WebSocket feed — the WS is a broadcast channel for server-initiated events;
 * this modal is an active capture session. No new network primitives needed.
 *
 * States
 * ──────
 *   scanning      Sending frames, no confident match yet
 *   recognised    Match found, attendance being marked / just marked
 *   already       Attendance already marked today → auto-close
 *   unknown       Low-confidence frame → keep scanning (no state change)
 *   error         Camera or permission error
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { attendanceService } from "../services/attendanceService";

// ── Config ────────────────────────────────────────────────────────────────
const CAPTURE_INTERVAL_MS = 500;   // one frame every 500 ms
const AUTO_CLOSE_DELAY_MS = 1_000; // close after marked/already-marked

// ── Tiny helpers ──────────────────────────────────────────────────────────

/** Format 0–1 similarity as a percentage string */
function pct(score) {
  if (score == null) return "—";
  return `${Math.round(score * 100)}%`;
}

/** Colour-code the similarity pill */
function scoreColour(score) {
  if (score == null) return "text-slate-400 bg-slate-800";
  if (score >= 0.82) return "text-emerald-300 bg-emerald-950/70 ring-1 ring-emerald-700/40";
  if (score >= 0.65) return "text-amber-300 bg-amber-950/70 ring-1 ring-amber-700/40";
  return "text-rose-300 bg-rose-950/70 ring-1 ring-rose-700/40";
}

// ── Scanning pulse ring ───────────────────────────────────────────────────
function ScanRing({ active }) {
  return (
    <span
      className={`pointer-events-none absolute inset-0 rounded-xl transition-opacity duration-500 ${
        active ? "opacity-100" : "opacity-0"
      }`}
      aria-hidden="true"
    >
      <span className="absolute inset-0 animate-ping rounded-xl border-2 border-indigo-500/40" />
    </span>
  );
}

// ── Bounding-box overlay ──────────────────────────────────────────────────
/**
 * Draws the face bounding box returned by the server onto the video.
 * `bbox` shape: { x, y, w, h } in the *original frame* pixel space.
 * We need to scale to the rendered <video> element dimensions.
 */
function BBoxOverlay({ bbox, videoNaturalSize, containerRef }) {
  if (!bbox || !videoNaturalSize || !containerRef.current) return null;

  const el = containerRef.current;
  const scaleX = el.offsetWidth / (videoNaturalSize.w || 640);
  const scaleY = el.offsetHeight / (videoNaturalSize.h || 480);

  const left = bbox.x * scaleX;
  const top = bbox.y * scaleY;
  const width = bbox.w * scaleX;
  const height = bbox.h * scaleY;

  return (
    <div
      className="pointer-events-none absolute border-2 border-indigo-400/80 transition-all duration-150"
      style={{
        left,
        top,
        width,
        height,
        borderRadius: 4,
        boxShadow: "0 0 0 1px rgba(99,102,241,0.25), inset 0 0 0 1px rgba(99,102,241,0.15)",
      }}
    />
  );
}

// ── Status overlay (marked / already-marked) ──────────────────────────────
function StatusOverlay({ phase, studentName }) {
  if (phase !== "recognised" && phase !== "already") return null;

  const isAlready = phase === "already";
  return (
    <div
      className={`absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-xl transition-all duration-300 ${
        isAlready
          ? "bg-amber-950/85"
          : "bg-emerald-950/85"
      }`}
    >
      {/* Icon */}
      <div
        className={`flex h-14 w-14 items-center justify-center rounded-full ring-2 ${
          isAlready
            ? "bg-amber-500/15 ring-amber-500/40"
            : "bg-emerald-500/15 ring-emerald-500/40"
        }`}
      >
        {isAlready ? (
          <svg className="h-7 w-7 text-amber-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ) : (
          <svg className="h-7 w-7 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        )}
      </div>

      {/* Text */}
      <div className="text-center px-4">
        <p className={`text-base font-semibold ${isAlready ? "text-amber-300" : "text-emerald-300"}`}>
          {isAlready ? "Already Marked" : "Attendance Marked"}
        </p>
        {studentName && (
          <p className="mt-0.5 text-sm text-slate-300">{studentName}</p>
        )}
        <p className="mt-1 text-xs text-slate-500">Closing…</p>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────

/**
 * AttendanceCameraModal
 *
 * Props
 * ─────
 * onClose      () => void        Called when the modal should unmount
 * onMarked     (record) => void  Called when a new attendance record is created
 * deviceId     string?           Forwarded to the recognition endpoint
 */
export default function AttendanceCameraModal({ onClose, onMarked, deviceId }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const containerRef = useRef(null); // wraps <video>, used for bbox scaling
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const inFlightRef = useRef(false);  // prevents overlapping requests
  const settledRef = useRef(false);   // true once we enter recognised/already

  const [phase, setPhase] = useState("init"); // init | scanning | recognised | already | error
  const [errorMsg, setErrorMsg] = useState("");

  // Recognition state shown in overlay / HUD
  const [studentName, setStudentName] = useState(null);
  const [studentCode, setStudentCode] = useState(null);
  const [similarity, setSimilarity] = useState(null);
  const [confidenceBand, setConfidenceBand] = useState(null);
  const [bbox, setBbox] = useState(null);
  const [videoNaturalSize, setVideoNaturalSize] = useState(null);

  // ── Camera management ───────────────────────────────────────────────────

  const stopCamera = useCallback(() => {
    clearInterval(intervalRef.current);
    inFlightRef.current = false;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setVideoNaturalSize({
          w: videoRef.current.videoWidth,
          h: videoRef.current.videoHeight,
        });
      }
      setPhase("scanning");
    } catch (err) {
      setPhase("error");
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setErrorMsg("Camera access denied. Allow camera permission and try again.");
      } else if (err.name === "NotFoundError") {
        setErrorMsg("No camera detected. Please connect a webcam and try again.");
      } else {
        setErrorMsg(`Camera error: ${err.message}`);
      }
    }
  }, []);

  // ── Frame capture & recognition ─────────────────────────────────────────

  const captureAndRecognise = useCallback(async () => {
    if (inFlightRef.current || settledRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    inFlightRef.current = true;
    try {
      // Snapshot current video frame
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85));
      if (!blob || settledRef.current) return;

      // POST frame to recognition endpoint
      const result = await attendanceService.identify(blob, deviceId);
      if (settledRef.current) return; // resolved while request was in-flight

      // Update natural size in case it wasn't ready at camera start
      if (video.videoWidth && !videoNaturalSize) {
        setVideoNaturalSize({ w: video.videoWidth, h: video.videoHeight });
      }

      // Update live HUD regardless of recognition result
      setSimilarity(result.similarity ?? null);
      setConfidenceBand(result.confidence_band ?? null);
      setBbox(result.bbox ?? null);

      if (result.recognized) {
        setStudentName(result.student_name ?? null);
        setStudentCode(result.student_code ?? null);

        settledRef.current = true;
        stopCamera();

        if (result.already_marked) {
          setPhase("already");
        } else {
          setPhase("recognised");
          onMarked?.(result.record ?? result);
        }
      }
      // If !recognized → keep scanning; HUD updates but phase stays "scanning"
    } catch (err) {
      // Network / server errors: log and continue scanning rather than crashing
      console.warn("[AttendanceCameraModal] identify error:", err);
    } finally {
      inFlightRef.current = false;
    }
  }, [deviceId, onMarked, stopCamera, videoNaturalSize]);

  // ── Auto-close after settled states ────────────────────────────────────

  useEffect(() => {
    if (phase !== "recognised" && phase !== "already") return;
    const t = setTimeout(() => {
      onClose();
    }, AUTO_CLOSE_DELAY_MS);
    return () => clearTimeout(t);
  }, [phase, onClose]);

  // ── Start interval when scanning ────────────────────────────────────────

  useEffect(() => {
    if (phase !== "scanning") return;
    intervalRef.current = setInterval(captureAndRecognise, CAPTURE_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [phase, captureAndRecognise]);

  // ── Lifecycle ───────────────────────────────────────────────────────────

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, [startCamera, stopCamera]);

  // ── Retry ───────────────────────────────────────────────────────────────

  const handleRetry = () => {
    settledRef.current = false;
    setPhase("init");
    setErrorMsg("");
    setBbox(null);
    setSimilarity(null);
    setStudentName(null);
    startCamera();
  };

  // ── Dismiss ─────────────────────────────────────────────────────────────

  const handleClose = () => {
    stopCamera();
    onClose();
  };

  // ── Render ──────────────────────────────────────────────────────────────

  const isSettled = phase === "recognised" || phase === "already";
  const isScanning = phase === "scanning";

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget && !isSettled) handleClose(); }}
    >
      {/* Panel */}
      <div
        className="relative mx-4 w-full max-w-lg overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-3">
            {/* Scanning pulse indicator */}
            <span className="relative flex h-2.5 w-2.5">
              {isScanning && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-60" />
              )}
              <span
                className={`relative inline-flex h-2.5 w-2.5 rounded-full transition-colors duration-300 ${
                  isSettled
                    ? phase === "recognised" ? "bg-emerald-400" : "bg-amber-400"
                    : isScanning ? "bg-indigo-400" : "bg-slate-600"
                }`}
              />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-slate-200">
                {isScanning ? "Scanning…" : isSettled ? (phase === "recognised" ? "Recognised" : "Already Marked") : "Camera"}
              </h2>
              <p className="text-xs text-slate-500">
                {isScanning
                  ? "Point the camera at a student's face"
                  : phase === "recognised"
                  ? `Marked present — ${studentName}`
                  : phase === "already"
                  ? `${studentName ?? "Student"} already marked today`
                  : "Initialising camera…"}
              </p>
            </div>
          </div>

          {!isSettled && (
            <button
              onClick={handleClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
              aria-label="Close"
            >
              <svg fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* ── Video area ── */}
        <div className="px-5 pt-5">
          <div
            ref={containerRef}
            className="relative overflow-hidden rounded-xl bg-black"
            style={{ aspectRatio: "4/3" }}
          >
            <video
              ref={videoRef}
              muted
              playsInline
              className={`h-full w-full object-cover transition-opacity duration-500 ${
                phase === "scanning" || isSettled ? "opacity-100" : "opacity-25"
              }`}
              style={{ transform: "scaleX(-1)" }}
              onLoadedMetadata={() => {
                if (videoRef.current) {
                  setVideoNaturalSize({
                    w: videoRef.current.videoWidth,
                    h: videoRef.current.videoHeight,
                  });
                }
              }}
            />

            {/* Hidden capture canvas */}
            <canvas ref={canvasRef} className="hidden" />

            {/* Bounding box (mirrored with video using scaleX(-1)) */}
            {isScanning && bbox && (
              <div style={{ transform: "scaleX(-1)", position: "absolute", inset: 0, pointerEvents: "none" }}>
                <BBoxOverlay
                  bbox={bbox}
                  videoNaturalSize={videoNaturalSize}
                  containerRef={containerRef}
                />
              </div>
            )}

            {/* Scanning corner guides */}
            {isScanning && (
              <div className="pointer-events-none absolute inset-0">
                {/* Top-left */}
                <span className="absolute left-3 top-3 h-5 w-5 border-l-2 border-t-2 border-indigo-500/60 rounded-tl" />
                {/* Top-right */}
                <span className="absolute right-3 top-3 h-5 w-5 border-r-2 border-t-2 border-indigo-500/60 rounded-tr" />
                {/* Bottom-left */}
                <span className="absolute bottom-3 left-3 h-5 w-5 border-b-2 border-l-2 border-indigo-500/60 rounded-bl" />
                {/* Bottom-right */}
                <span className="absolute bottom-3 right-3 h-5 w-5 border-b-2 border-r-2 border-indigo-500/60 rounded-br" />
              </div>
            )}

            {/* Init spinner */}
            {phase === "init" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                <p className="text-xs text-slate-400">Starting camera…</p>
              </div>
            )}

            {/* Settled overlay */}
            <StatusOverlay phase={phase} studentName={studentName} />
          </div>
        </div>

        {/* ── HUD strip ── */}
        <div className="px-5 py-4">
          {phase === "error" ? (
            /* Error state */
            <div className="space-y-3 rounded-xl border border-rose-800/40 bg-rose-950/40 p-4">
              <div className="flex items-start gap-2.5">
                <svg className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                <p className="text-sm text-rose-400">{errorMsg}</p>
              </div>
              <button
                onClick={handleRetry}
                className="w-full rounded-lg bg-rose-900/60 py-2 text-xs font-semibold text-rose-300 transition hover:bg-rose-900"
              >
                Try Again
              </button>
            </div>
          ) : (
            /* Recognition HUD */
            <div className="flex items-center justify-between gap-4">
              {/* Student info */}
              <div className="min-w-0">
                {studentName ? (
                  <>
                    <p className="truncate text-sm font-semibold text-slate-200">{studentName}</p>
                    {studentCode && (
                      <p className="truncate text-xs text-slate-500">{studentCode}</p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-slate-500">
                    {isScanning ? "No match yet — keep scanning" : "—"}
                  </p>
                )}
              </div>

              {/* Similarity + confidence */}
              <div className="flex shrink-0 items-center gap-2">
                {confidenceBand && (
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-400 ring-1 ring-slate-700">
                    {confidenceBand}
                  </span>
                )}
                <span
                  className={`rounded-md px-2.5 py-0.5 text-xs font-semibold tabular-nums transition-colors duration-300 ${scoreColour(similarity)}`}
                >
                  {pct(similarity)}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        {!isSettled && phase !== "error" && (
          <div className="flex items-center justify-between border-t border-slate-800/60 px-5 py-3">
            <p className="text-xs text-slate-600">
              {isScanning
                ? "Frames with no face are skipped automatically."
                : "Initialising…"}
            </p>
            <button
              onClick={handleClose}
              className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
