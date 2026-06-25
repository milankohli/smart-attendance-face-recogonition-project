/**
 * recognitionSocket.js
 * ────────────────────────────────────────────────────────────────────────────
 * WebSocket manager for the real-time recognition feed.
 *
 * The server is expected to push JSON messages of this shape on the
 * `recognition` channel:
 *
 *   { type: "recognition_event", payload: RecognitionResponse }
 *   { type: "heartbeat" }
 *   { type: "error", message: string }
 *
 * Usage:
 *   const socket = createRecognitionSocket({
 *     onEvent: (event) => console.log(event),
 *     onConnect: () => setConnected(true),
 *     onDisconnect: () => setConnected(false),
 *     onError: (err) => console.error(err),
 *   });
 *   socket.connect();
 *   // …later…
 *   socket.disconnect();
 * ────────────────────────────────────────────────────────────────────────────
 */

const WS_BASE_URL =
  (import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000") + "/ws/recognition";

const RECONNECT_DELAY_MS = 3_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const HEARTBEAT_TIMEOUT_MS = 30_000;

/**
 * @typedef {Object} RecognitionSocketOptions
 * @property {(event: object) => void}  onEvent       Called for each recognition event
 * @property {() => void}               [onConnect]   Called when socket opens
 * @property {() => void}               [onDisconnect] Called when socket closes
 * @property {(err: string) => void}    [onError]     Called on error messages
 * @property {string}                   [deviceId]    Identify this client to the server
 */

/**
 * Factory — returns a socket controller with connect / disconnect / send.
 * @param {RecognitionSocketOptions} options
 */
export function createRecognitionSocket(options = {}) {
  const { onEvent, onConnect, onDisconnect, onError, deviceId } = options;

  let ws = null;
  let reconnectAttempts = 0;
  let reconnectTimer = null;
  let heartbeatTimer = null;
  let manualClose = false;

  // ── Heartbeat ──────────────────────────────────────────────────────────────
  function resetHeartbeat() {
    clearTimeout(heartbeatTimer);
    heartbeatTimer = setTimeout(() => {
      console.warn("[RecognitionSocket] Heartbeat timeout — reconnecting…");
      ws?.close();
    }, HEARTBEAT_TIMEOUT_MS);
  }

  // ── Connect ────────────────────────────────────────────────────────────────
  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return;

    manualClose = false;
    const token = localStorage.getItem("access_token");
    const url = new URL(WS_BASE_URL);
    if (token) url.searchParams.set("token", token);
    if (deviceId) url.searchParams.set("device_id", deviceId);

    ws = new WebSocket(url.toString());

    ws.onopen = () => {
      console.info("[RecognitionSocket] Connected");
      reconnectAttempts = 0;
      resetHeartbeat();
      onConnect?.();
    };

    ws.onmessage = (evt) => {
      resetHeartbeat();
      let msg;
      try {
        msg = JSON.parse(evt.data);
      } catch {
        return; // Ignore non-JSON frames
      }

      switch (msg.type) {
        case "recognition_event":
          onEvent?.(msg.payload);
          break;
        case "heartbeat":
          // Server ping — no-op, resetHeartbeat() already called above
          break;
        case "error":
          onError?.(msg.message ?? "Unknown socket error");
          break;
        default:
          // Forward unknown message types verbatim
          onEvent?.(msg);
      }
    };

    ws.onerror = () => {
      onError?.("WebSocket connection error");
    };

    ws.onclose = () => {
      clearTimeout(heartbeatTimer);
      onDisconnect?.();
      if (!manualClose && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        const delay = RECONNECT_DELAY_MS * Math.min(reconnectAttempts, 5);
        console.info(
          `[RecognitionSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})…`
        );
        reconnectTimer = setTimeout(connect, delay);
      }
    };
  }

  // ── Disconnect ─────────────────────────────────────────────────────────────
  function disconnect() {
    manualClose = true;
    clearTimeout(reconnectTimer);
    clearTimeout(heartbeatTimer);
    if (ws) {
      ws.close();
      ws = null;
    }
  }

  // ── Send arbitrary JSON ────────────────────────────────────────────────────
  function send(payload) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  /** true while the underlying WebSocket is open */
  function isConnected() {
    return ws?.readyState === WebSocket.OPEN;
  }

  return { connect, disconnect, send, isConnected };
}

// ── React hook wrapper ─────────────────────────────────────────────────────
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useRecognitionSocket — React hook that manages lifecycle automatically.
 *
 * @param {{ onEvent: Function, autoConnect?: boolean, deviceId?: string }} opts
 * @returns {{ connected: boolean, connect: Function, disconnect: Function }}
 */
export function useRecognitionSocket({ onEvent, autoConnect = false, deviceId } = {}) {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  // Keep onEvent in a ref so it never causes reconnect on re-render
  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    const socket = createRecognitionSocket({
      onEvent: (evt) => onEventRef.current?.(evt),
      onConnect: () => setConnected(true),
      onDisconnect: () => setConnected(false),
      onError: (err) => console.error("[RecognitionSocket]", err),
      deviceId,
    });
    socketRef.current = socket;
    if (autoConnect) socket.connect();

    return () => socket.disconnect();
  }, [autoConnect, deviceId]); // intentionally stable deps

  const connect = useCallback(() => socketRef.current?.connect(), []);
  const disconnect = useCallback(() => socketRef.current?.disconnect(), []);

  return { connected, connect, disconnect };
}
