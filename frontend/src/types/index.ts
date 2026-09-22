// Types mirroring the FastAPI backend payloads (see src/aegisflight/backend).

export interface Telemetry {
  lat: number | null;
  lon: number | null;
  alt_msl: number | null;
  rel_alt: number | null;
  groundspeed: number | null;
  heading: number | null;
  battery_voltage: number | null;
  battery_remaining: number | null;
  satellites: number | null;
  flight_mode: string | null;
  armed: boolean | null;
}

export interface Threat {
  threat: boolean;
  threat_score: number;
  severity: string;
  attack_type: string;
  confidence: number;
  evidence: string[];
  detector_scores: Record<string, number>;
  contributing_detectors: string[];
  integrity_status: string;
  latency_ms: number;
  is_alert: boolean;
}

export interface Update {
  type: "update";
  sim: boolean;
  t: number;
  telemetry: Telemetry;
  attack_active: string | null;
  threat?: Threat;
}

export interface AlertRow {
  id: number | null;
  t: number;
  attack_type: string;
  severity: string;
  threat_score: number;
  confidence: number;
  evidence: string[];
  integrity_status: string;
  latency_ms: number;
}

export interface Status {
  running: boolean;
  sim: boolean;
  sim_time_s: number;
  uptime_s: number;
  active_attack: string | null;
  ml_available: boolean;
  threat: boolean;
  severity: string;
  attack_type: string;
  threat_score: number;
  integrity_status: string;
  run_id: string;
}

export interface Metrics {
  messages_processed: number;
  decisions: number;
  alerts: number;
  throughput_msgs_per_s: number;
  last_latency_ms: number | null;
  event_log: { count: number; chain_ok: boolean };
  ml_available: boolean;
}
