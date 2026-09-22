import type { AlertRow } from "../types";

export function AlertsPanel({ alerts }: { alerts: AlertRow[] }) {
  return (
    <div className="panel">
      <h2>Event history — {alerts.length} logged alert(s)</h2>
      {alerts.length === 0 ? (
        <div className="evidence empty">No alerts logged yet. Inject an attack to generate events.</div>
      ) : (
        <ul className="alerts">
          {alerts.map((a, i) => (
            <li className="alert" key={a.id ?? i} style={{ borderLeftColor: `var(--${sevVar(a.severity)})` }}>
              <div className="row1">
                <span className={`atk sev-${a.severity}`}>{a.attack_type.replace(/_/g, " ")}</span>
                <span className="time">t={a.t.toFixed(1)}s · {a.severity}</span>
              </div>
              <div className="ev">
                score {a.threat_score.toFixed(2)} · conf {a.confidence.toFixed(2)} ·
                {" "}{a.evidence[0] ?? "—"}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function sevVar(sev: string): string {
  return { NORMAL: "ok", WATCH: "watch", SUSPICIOUS: "warn", HIGH: "high", CRITICAL: "crit" }[sev] ?? "high";
}
