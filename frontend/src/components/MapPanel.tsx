import type { Threat } from "../types";

interface Props {
  track: Array<[number, number]>;
  scoreHistory: Array<{ t: number; score: number }>;
  threat: Threat | null;
}

// Simple self-scaling 2D position plot (lat/lon -> metres from track centroid).
export function MapPanel({ track, scoreHistory, threat }: Props) {
  const W = 640, H = 380, pad = 24;
  let path = "";
  let head: [number, number] | null = null;
  if (track.length > 1) {
    const lats = track.map((p) => p[0]);
    const lons = track.map((p) => p[1]);
    const lat0 = (Math.min(...lats) + Math.max(...lats)) / 2;
    const mPerLat = 111_320;
    const mPerLon = 111_320 * Math.cos((lat0 * Math.PI) / 180);
    const xs = track.map((p) => (p[1] - lons[0]) * mPerLon);
    const ys = track.map((p) => (p[0] - lats[0]) * mPerLat);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const span = Math.max(maxX - minX, maxY - minY, 20);
    const sx = (x: number) => pad + ((x - minX) / span) * (W - 2 * pad);
    const sy = (y: number) => H - pad - ((y - minY) / span) * (H - 2 * pad);
    path = track.map((_, i) => `${i ? "L" : "M"}${sx(xs[i]).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join(" ");
    head = [sx(xs[xs.length - 1]), sy(ys[ys.length - 1])];
  }

  const active = threat?.threat;
  const color = active ? "var(--high)" : "var(--accent)";

  // sparkline
  const SW = 640, SH = 70;
  let spark = "";
  if (scoreHistory.length > 1) {
    const n = scoreHistory.length;
    spark = scoreHistory
      .map((h, i) => `${i ? "L" : "M"}${((i / (n - 1)) * SW).toFixed(1)},${(SH - h.score * SH).toFixed(1)}`)
      .join(" ");
  }
  const thrY = SH - 0.45 * SH;

  return (
    <div className="panel">
      <h2>Position track & threat timeline (simulated)</h2>
      <div className="map-wrap">
        <svg className="map" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
          <rect x="0" y="0" width={W} height={H} fill="#0d151d" />
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1={f * W} y1="0" x2={f * W} y2={H} stroke="#182430" strokeWidth="1" />
          ))}
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={"h" + f} x1="0" y1={f * H} x2={W} y2={f * H} stroke="#182430" strokeWidth="1" />
          ))}
          {path && <path d={path} fill="none" stroke={color} strokeWidth="2" opacity="0.9" />}
          {head && <circle cx={head[0]} cy={head[1]} r="6" fill={color} stroke="#fff" strokeWidth="1.5" />}
          <text x={pad} y={H - 8} fill="#5b6b7a" fontSize="11" fontFamily="monospace">
            self-scaled local frame · {track.length} fixes
          </text>
        </svg>
      </div>
      <svg className="spark" viewBox={`0 0 ${SW} ${SH}`} preserveAspectRatio="none">
        <line x1="0" y1={thrY} x2={SW} y2={thrY} stroke="#4a5563" strokeDasharray="4 4" strokeWidth="1" />
        {spark && <path d={spark} fill="none" stroke={color} strokeWidth="2" />}
      </svg>
      <div className="sub" style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}>
        threat score over time — dashed line = alert threshold (0.45)
      </div>
    </div>
  );
}
