import { AlertsPanel } from "./components/AlertsPanel";
import { ControlPanel } from "./components/ControlPanel";
import { Header } from "./components/Header";
import { MapPanel } from "./components/MapPanel";
import { DetectorPanel, EvidencePanel, ThreatPanel, TelemetryPanel } from "./components/panels";
import { useLiveData } from "./hooks/useLiveData";

export default function App() {
  const live = useLiveData();
  const m = live.metrics;
  return (
    <div className="app">
      <Header
        connected={live.connected}
        simTime={live.t}
        mlAvailable={m?.ml_available ?? false}
      />
      <div className="grid">
        <div className="col">
          <ThreatPanel threat={live.threat} />
          <DetectorPanel threat={live.threat} />
          <ControlPanel activeAttack={live.attackActive} />
        </div>
        <div className="col">
          <MapPanel track={live.track} scoreHistory={live.scoreHistory} threat={live.threat} />
          <TelemetryPanel tele={live.telemetry} />
          <EvidencePanel threat={live.threat} />
        </div>
        <div className="col">
          <AlertsPanel alerts={live.alerts} />
        </div>
      </div>

      <div className="metrics-bar">
        <span>messages&nbsp;<b>{m?.messages_processed ?? 0}</b></span>
        <span>decisions&nbsp;<b>{m?.decisions ?? 0}</b></span>
        <span>alerts&nbsp;<b>{m?.alerts ?? 0}</b></span>
        <span>throughput&nbsp;<b>{m?.throughput_msgs_per_s ?? 0}</b>&nbsp;msg/s</span>
        <span>last latency&nbsp;<b>{m?.last_latency_ms != null ? m.last_latency_ms.toFixed(2) : "—"}</b>&nbsp;ms</span>
        <span>
          event log&nbsp;<b>{m?.event_log.count ?? 0}</b>&nbsp;·&nbsp;chain&nbsp;
          <b style={{ color: m?.event_log.chain_ok === false ? "var(--crit)" : "var(--ok)" }}>
            {m?.event_log.chain_ok === false ? "BROKEN" : "OK"}
          </b>
        </span>
      </div>
      <div className="foot">
        AegisFlight is a Stage-1 proof-of-concept. All flight data and attacks shown are
        <b> local simulations</b> — this dashboard does not connect to a real UAV.
      </div>
    </div>
  );
}
