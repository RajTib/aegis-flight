// Presentation-only classifier: derive which detector a piece of evidence came
// from, purely from the (unmodified) evidence text. The backend flattens all
// detector evidence into one string[] with no source prefix; each detector's
// vocabulary is distinctive, so we can tag lines for display without ever
// changing their content. Falls back to "signal" when a line is unrecognised.

export type EvidenceSource = "physics" | "protocol" | "ml" | "firmware" | "signal";

interface Rule { src: EvidenceSource; needles: string[]; }

// Ordered: check the most specific vocabularies first.
const RULES: Rule[] = [
  { src: "ml", needles: ["ml anomaly", "anomaly score", "driver:"] },
  {
    src: "firmware",
    needles: ["sha-256", "component missing", "unexpected component",
      "components verified", "firmware manifest"],
  },
  {
    src: "protocol",
    needles: ["message flood", "message-rate", "msg/s", "sequence gap",
      "rogue telemetry", "heartbeat", "gps dropout", "gnss fix",
      "unexpected source", "unsigned messages", "signed ratio", "sensitive:"],
  },
  {
    src: "physics",
    needles: ["residual", "altitude mismatch", "speed mismatch", "altitude rate",
      "acceleration", "battery voltage", "battery collapse", "heading/course",
      "gps/baro", "gps/vfr"],
  },
];

export function classifyEvidence(line: string): EvidenceSource {
  const s = line.toLowerCase();
  for (const rule of RULES) {
    if (rule.needles.some((n) => s.includes(n))) return rule.src;
  }
  return "signal";
}

export const SOURCE_LABEL: Record<EvidenceSource, string> = {
  physics: "Physics",
  protocol: "Protocol",
  ml: "ML",
  firmware: "Firmware",
  signal: "Signal",
};

// Distinct ordered sources present in a set of evidence lines.
export function sourcesOf(evidence: string[]): EvidenceSource[] {
  const order: EvidenceSource[] = ["physics", "protocol", "ml", "firmware", "signal"];
  const seen = new Set(evidence.map(classifyEvidence));
  return order.filter((s) => seen.has(s));
}
