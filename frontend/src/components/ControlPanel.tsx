import { useState } from "react";
import { api } from "../services/api";

const ATTACKS: Array<{ id: string; label: string }> = [
  { id: "gps_spoofing", label: "GPS Spoofing" },
  { id: "mavlink_anomaly", label: "MAVLink Anomaly" },
  { id: "command_injection", label: "Command Injection" },
  { id: "telemetry_manipulation", label: "Telemetry Manip." },
  { id: "dos", label: "Denial of Service" },
  { id: "firmware_integrity", label: "Firmware Tamper" },
];

export function ControlPanel({ activeAttack }: { activeAttack: string | null }) {
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <div className="panel">
      <h2>Simulation Controls</h2>
      <div className="controls">
        <button className="primary" disabled={busy} onClick={() => run(api.start)}>▶ Start</button>
        <button disabled={busy} onClick={() => run(api.stop)}>⏸ Stop</button>
        <button className="danger" disabled={busy} onClick={() => run(api.reset)}>↻ Reset</button>
      </div>
      <h2 style={{ marginTop: 16 }}>Inject Attack (safe simulation)</h2>
      <div className="attack-grid">
        {ATTACKS.map((a) => (
          <button
            key={a.id}
            className={activeAttack === a.id ? "active" : ""}
            disabled={busy}
            onClick={() => run(() => api.attack(a.id))}
          >
            {a.label}
          </button>
        ))}
      </div>
      <button
        style={{ marginTop: 8, width: "100%" }}
        className={activeAttack ? "primary" : ""}
        disabled={busy || !activeAttack}
        onClick={() => run(() => api.attack("none"))}
      >
        ■ Clear attack {activeAttack ? `(${activeAttack.replace(/_/g, " ")})` : ""}
      </button>
    </div>
  );
}
