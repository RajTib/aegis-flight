interface Props {
  connected: boolean;
  simTime: number;
  mlAvailable: boolean;
}

export function Header({ connected, simTime, mlAvailable }: Props) {
  const mm = Math.floor(simTime / 60);
  const ss = Math.floor(simTime % 60);
  return (
    <header className="header">
      <div>
        <h1>AegisFlight</h1>
        <div className="sub">UAV Cyber-Physical Intrusion Detection System</div>
      </div>
      <span className="badge sim">● Simulation</span>
      <div className="spacer" />
      <div className="sub">
        sim&nbsp;t&nbsp;=&nbsp;<b style={{ fontFamily: "var(--mono)" }}>
          {mm}:{ss.toString().padStart(2, "0")}
        </b>
      </div>
      <span className="badge" style={{ background: "#12232f", color: "var(--muted)", border: "1px solid var(--border)" }}>
        ML {mlAvailable ? "on" : "off"}
      </span>
      <span className={`badge ${connected ? "conn-on" : "conn-off"}`}>
        {connected ? "● Connected" : "○ Disconnected"}
      </span>
    </header>
  );
}
