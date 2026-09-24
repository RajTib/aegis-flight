import { AlertsPanel } from "./components/AlertsPanel";
import { ControlPanel } from "./components/ControlPanel";
import { Header } from "./components/Header";
import { MapPanel } from "./components/MapPanel";
import { DetectorPanel, EvidencePanel, ThreatPanel, TelemetryPanel } from "./components/panels";
import {
  CoveragePanel,
  IntegrationPanel,
  RuntimePanel,
  ValidationPanel,
} from "./components/evalPanels";
import { useLiveData } from "./hooks/useLiveData";

export default function App() {
  const live = useLiveData();
  const m = live.metrics;
  const chainOk = m?.event_log.chain_ok !== false;

  return (
    <div className="app">
      <Header
        connected={live.connected}
        simTime={live.t}
        mlAvailable={m?.ml_available ?? false}
      />

      <main className="console">
        {/* 1. primary: threat assessment · flight track · incidents */}
        <section className="ops">
          <div className="stack">
            <ThreatPanel threat={live.threat} />
            <DetectorPanel threat={live.threat} />
          </div>
          <MapPanel track={live.track} scoreHistory={live.scoreHistory} threat={live.threat} />
          <AlertsPanel alerts={live.alerts} />
        </section>

        {/* 2. secondary: runtime performance · attack-vector coverage */}
        <section className="secondary">
          <RuntimePanel metrics={m} distance={live.distance} />
          <CoveragePanel activeAttack={live.attackActive} />
        </section>

        {/* 3. telemetry */}
        <TelemetryPanel tele={live.telemetry} />

        {/* 4. evidence · controls */}
        <section className="lower">
          <EvidencePanel threat={live.threat} />
          <ControlPanel activeAttack={live.attackActive} />
        </section>

        {/* 5. reference: integration · validation evidence */}
        <section className="reference">
          <IntegrationPanel />
          <ValidationPanel />
        </section>
      </main>

      <div className="metrics-bar">
        <span className="m-tag">Live</span>
        <span className="m">Messages <b>{m?.messages_processed ?? 0}</b></span>
        <span className="m">Decisions <b>{m?.decisions ?? 0}</b></span>
        <span className="m">Alerts <b>{m?.alerts ?? 0}</b></span>
        <span className="m">Distance <b>{((live.distance ?? 0) / 1000).toFixed(2)}</b> km</span>
        <span className="m">Throughput <b>{m?.throughput_msgs_per_s ?? 0}</b> msg/s</span>
        <span className="m">Decision compute <b>{m?.decision_compute_ms != null ? m.decision_compute_ms.toFixed(2) : "—"}</b> ms</span>
        <span className="m">
          Event log <b>{m?.event_log.count ?? 0}</b> · chain{" "}
          <b style={{ color: chainOk ? "var(--ok)" : "var(--crit)" }}>{chainOk ? "OK" : "BROKEN"}</b>
        </span>
      </div>
      <div className="foot">
        AegisFlight is a Stage-1 proof-of-concept. All flight data and attacks shown are{" "}
        <b>local simulations</b> — this dashboard does not connect to a real UAV.
      </div>
    </div>
  );
}
