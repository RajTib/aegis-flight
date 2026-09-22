import type { Telemetry, Threat } from "../types";

const DETECTOR_LABELS: Record<string, string> = {
  protocol_rule: "Protocol / rule",
  physics_consistency: "Physics consistency",
  ml_anomaly: "ML anomaly",
  firmware_integrity: "Firmware integrity",
};

export function ThreatPanel({ threat }: { threat: Threat | null }) {
  const sev = threat?.threat ? threat.severity : "NORMAL";
  const score = threat?.threat_score ?? 0;
  const attack = threat?.threat ? threat.attack_type : "NONE";
  return (
    <div className="panel">
      <h2>Threat State</h2>
      <div className="threat-hero">
        <div className={`threat-state sev-${sev}`}>{threat?.threat ? sev : "NORMAL"}</div>
        <div className={`threat-attack sev-${sev}`}>{attack.replace(/_/g, " ")}</div>
      </div>
      <div className="gauge">
        <div className={`bg-${sev}`} style={{ width: `${Math.min(100, score * 100)}%` }} />
      </div>
      <div className="kv"><span className="k">Threat score</span><span className="v">{score.toFixed(3)}</span></div>
      <div className="kv"><span className="k">Confidence</span><span className="v">{(threat?.confidence ?? 0).toFixed(2)}</span></div>
      <div className="kv"><span className="k">Detection latency</span><span className="v">{(threat?.latency_ms ?? 0).toFixed(2)} ms</span></div>
      <div className="kv">
        <span className="k">Firmware</span>
        <span className={`v ${threat?.integrity_status === "INVALID" ? "sev-CRITICAL" : "sev-NORMAL"}`}>
          {threat?.integrity_status ?? "VALID"}
        </span>
      </div>
    </div>
  );
}

export function DetectorPanel({ threat }: { threat: Threat | null }) {
  const scores = threat?.detector_scores ?? {};
  return (
    <div className="panel">
      <h2>Detector Contributions</h2>
      {Object.keys(DETECTOR_LABELS).map((key) => {
        const v = scores[key] ?? 0;
        return (
          <div className="det-row" key={key}>
            <div className="top">
              <span>{DETECTOR_LABELS[key]}</span>
              <span style={{ fontFamily: "var(--mono)" }}>{v.toFixed(2)}</span>
            </div>
            <div className="det-bar"><div style={{ width: `${Math.min(100, v * 100)}%` }} /></div>
          </div>
        );
      })}
    </div>
  );
}

export function EvidencePanel({ threat }: { threat: Threat | null }) {
  const ev = threat?.threat ? threat.evidence : [];
  return (
    <div className="panel">
      <h2>Evidence — why this alert?</h2>
      {ev.length ? (
        <ul className="evidence">
          {ev.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      ) : (
        <div className="evidence empty">No anomalies — telemetry consistent with normal flight.</div>
      )}
    </div>
  );
}

function cell(label: string, value: string, unit = "") {
  return (
    <div className="tele-cell" key={label}>
      <div className="label">{label}</div>
      <div className="value">{value}<span className="unit"> {unit}</span></div>
    </div>
  );
}

export function TelemetryPanel({ tele }: { tele: Telemetry | null }) {
  const n = (x: number | null | undefined, d = 1) => (x == null ? "—" : x.toFixed(d));
  return (
    <div className="panel">
      <h2>Vehicle Telemetry</h2>
      <div className="tele-grid">
        {cell("Rel. altitude", n(tele?.rel_alt, 1), "m")}
        {cell("Ground speed", n(tele?.groundspeed, 1), "m/s")}
        {cell("Heading", n(tele?.heading, 0), "°")}
        {cell("Battery", n(tele?.battery_remaining, 0), "%")}
        {cell("Voltage", n(tele?.battery_voltage, 2), "V")}
        {cell("GPS sats", tele?.satellites != null ? String(tele.satellites) : "—")}
        {cell("Flight mode", tele?.flight_mode ?? "—")}
        {cell("Armed", tele?.armed == null ? "—" : tele.armed ? "YES" : "no")}
      </div>
    </div>
  );
}
