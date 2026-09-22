import { useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../services/api";
import type { AlertRow, Metrics, Telemetry, Threat, Update } from "../types";

export interface LiveState {
  connected: boolean;
  t: number;
  telemetry: Telemetry | null;
  threat: Threat | null;
  attackActive: string | null;
  track: Array<[number, number]>; // recent [lat, lon]
  scoreHistory: Array<{ t: number; score: number }>;
  alerts: AlertRow[];
  metrics: Metrics | null;
}

const MAX_TRACK = 400;
const MAX_HISTORY = 240;

export function useLiveData(): LiveState {
  const [connected, setConnected] = useState(false);
  const [t, setT] = useState(0);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [threat, setThreat] = useState<Threat | null>(null);
  const [attackActive, setAttackActive] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const trackRef = useRef<Array<[number, number]>>([]);
  const histRef = useRef<Array<{ t: number; score: number }>>([]);
  const [, force] = useState(0);

  // WebSocket live telemetry stream (auto-reconnect).
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as Update;
        if (msg.type !== "update") return;
        setT(msg.t);
        setTelemetry(msg.telemetry);
        setAttackActive(msg.attack_active);
        if (msg.telemetry.lat != null && msg.telemetry.lon != null) {
          const tr = trackRef.current;
          tr.push([msg.telemetry.lat, msg.telemetry.lon]);
          if (tr.length > MAX_TRACK) tr.shift();
        }
        if (msg.threat) {
          setThreat(msg.threat);
          const h = histRef.current;
          h.push({ t: msg.t, score: msg.threat.threat_score });
          if (h.length > MAX_HISTORY) h.shift();
          force((n) => n + 1);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, []);

  // Poll REST for alerts + metrics.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [ev, m] = await Promise.all([api.events(30), api.metrics()]);
        if (!alive) return;
        setAlerts(ev.events);
        setMetrics(m);
      } catch {
        /* backend not ready */
      }
    };
    tick();
    const id = window.setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return {
    connected,
    t,
    telemetry,
    threat,
    attackActive,
    track: trackRef.current,
    scoreHistory: histRef.current,
    alerts,
    metrics,
  };
}
