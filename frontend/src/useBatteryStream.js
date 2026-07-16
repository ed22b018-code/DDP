// -----------------------------------------------------------------------------
// useBatteryStream.js -- a custom React hook that manages the live WebSocket.
// -----------------------------------------------------------------------------
// A "hook" is a reusable piece of React logic. This one:
//   * opens the WebSocket to the backend
//   * keeps the latest tick (state + prediction + recommendation + flags)
//   * keeps a rolling history of samples for the time-series charts
//   * keeps a scrolling list of alerts
//   * auto-reconnects if the connection drops (so the UI recovers on its own)
//
// It intentionally does NOT use localStorage/sessionStorage (per project rules)
// -- everything lives in React state in memory.

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_URL } from "./api";

const MAX_HISTORY = 120; // how many samples to keep on the charts
const MAX_ALERTS = 40; // how many alert entries to keep in the feed

export function useBatteryStream(enabled) {
  const [connected, setConnected] = useState(false);
  const [latest, setLatest] = useState(null); // the most recent full tick
  const [history, setHistory] = useState([]); // rolling V/I/T samples
  const [alerts, setAlerts] = useState([]); // scrolling alert feed

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  // Remember the signature of the last alert set so we only append a new feed
  // entry when the active alerts actually change (avoids spamming the feed).
  const lastAlertKey = useRef("");

  const connect = useCallback(() => {
    // Don't open a second socket if one is already open.
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    let ws;
    try {
      ws = new WebSocket(WS_URL);
    } catch (err) {
      // If constructing the socket fails, try again shortly.
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return; // ignore malformed messages instead of crashing
      }
      if (msg.type !== "tick") return;

      setLatest(msg);

      // Append this sample to the rolling chart history.
      const s = msg.state;
      setHistory((prev) => {
        const next = [
          ...prev,
          {
            t: s.t,
            voltage_v: s.voltage_v,
            current_a: s.current_a,
            temperature_c: s.temperature_c,
          },
        ];
        // Keep only the most recent MAX_HISTORY points.
        return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
      });

      // Update the alert feed only when the active alert set changes.
      const flags = msg.flags || [];
      const key = flags.map((f) => f.code).sort().join("|");
      if (key !== lastAlertKey.current && flags.length > 0) {
        lastAlertKey.current = key;
        const stamp = new Date().toLocaleTimeString();
        setAlerts((prev) => {
          const newEntries = flags.map((f) => ({
            ...f,
            time: stamp,
            id: `${stamp}-${f.code}-${Math.random().toString(36).slice(2, 7)}`,
          }));
          const merged = [...newEntries, ...prev];
          return merged.slice(0, MAX_ALERTS);
        });
      } else if (flags.length === 0) {
        lastAlertKey.current = "";
      }
    };

    ws.onclose = () => {
      setConnected(false);
      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will fire next and handle reconnection.
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimer.current) return;
    reconnectTimer.current = setTimeout(() => {
      reconnectTimer.current = null;
      connect();
    }, 1500); // retry every 1.5s until the backend is back
  }, [connect]);

  useEffect(() => {
    if (!enabled) return undefined;
    connect();
    // Cleanup when the component unmounts or `enabled` turns off.
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
    };
  }, [enabled, connect]);

  return { connected, latest, history, alerts };
}
