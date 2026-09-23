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
      <div className="brand">
        <h1>
          <span className="mark">Aegis</span>Flight
        </h1>
        <div className="tagline">UAV Cyber-Physical Intrusion Detection System</div>
      </div>

      <div className="status-rail">
        <div className="stat">
          <span className="dot sim" />
          <span className="val">Simulation</span>
        </div>
        <div className="stat">
          <span>Mission clock</span>
          <span className="val mono">
            {mm}:{ss.toString().padStart(2, "0")}
          </span>
        </div>
        <div className="stat">
          <span className={`dot ${mlAvailable ? "on" : "idle"}`} />
          <span>ML engine</span>
          <span className="val">{mlAvailable ? "Online" : "Offline"}</span>
        </div>
        <div className="stat">
          <span className={`dot ${connected ? "on" : "off"}`} />
          <span className="val">{connected ? "Connected" : "Disconnected"}</span>
        </div>
      </div>
    </header>
  );
}
