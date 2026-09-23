import type { AlertRow } from "../types";
import { sourcesOf, SOURCE_LABEL } from "../lib/evidence";

export function AlertsPanel({ alerts }: { alerts: AlertRow[] }) {
  return (
    <div className="panel">
      <header>
        <span className="panel-title">Incident History</span>
        <span className="panel-note">{alerts.length} logged</span>
      </header>

      {alerts.length === 0 ? (
        <div className="empty">
          No incidents logged. Inject an attack to generate a tamper-evident
          event record.
        </div>
      ) : (
        <ul className="incidents">
          {alerts.map((a, i) => {
            const sources = sourcesOf(a.evidence);
            return (
              <li className={`incident lvl-${a.severity}`} key={a.id ?? i}>
                <div className="i-head">
                  <span className="i-name">{a.attack_type.replace(/_/g, " ")}</span>
                  <span className={`i-sev sev-${a.severity}`}>{a.severity}</span>
                </div>
                <div className="i-meta">
                  t={a.t.toFixed(1)}s · score {a.threat_score.toFixed(2)} · conf {a.confidence.toFixed(2)}
                </div>
                {a.evidence[0] && <div className="i-ev">{a.evidence[0]}</div>}
                {sources.length > 0 && (
                  <div className="i-src">
                    {sources.map((s) => (
                      <span className="src-tag" key={s}>{SOURCE_LABEL[s]}</span>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
