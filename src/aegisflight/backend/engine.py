"""Live simulation + IDS engine for the dashboard backend.

Drives the same deterministic pipeline as the benchmark, but in *real time*:
each tick advances the simulator, encodes/decodes genuine MAVLink, runs the IDS,
and pushes an update to every connected WebSocket subscriber. Attacks can be
injected and cleared at runtime (the demo's whole point) by swapping the
source's active attack — the source reads ``self.attack`` fresh each tick.

Everything here is a SIMULATION: the ``sim: true`` flag rides on every update so
the dashboard can never misrepresent simulated activity as a real UAV.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import time
from collections import deque
from pathlib import Path

import numpy as np

from ..attacks import ATTACK_REGISTRY, build_attack
from ..attacks.base import NoAttack
from ..config import AegisConfig, load_config
from ..core.enums import IntegrityStatus
from ..core.geo import haversine_m
from ..logging import EventStore
from ..pipeline import IDSPipeline
from ..sources.stream import SimulatedTelemetrySource

# Long "live" duration so the survey pattern flies continuously for a demo.
_LIVE_DURATION_S = 100_000.0

# Rolling window (wall-clock seconds) used to report *current* live throughput.
# A window — rather than messages-since-boot / uptime — keeps the displayed rate
# honest across resets (counters restart but a boot-time denominator would not).
_THROUGHPUT_WINDOW_S = 5.0


class LiveEngine:
    def __init__(self, cfg: AegisConfig | None = None, db_path: str | None = None,
                 model_path: str = "models/isoforest.joblib") -> None:
        self.cfg = cfg or load_config()
        self.cfg.simulation["duration_s"] = _LIVE_DURATION_S
        self.model_path = model_path if Path(model_path).exists() else None
        self.db_path = db_path or "artifacts/aegisflight_live.sqlite"
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.dt = 1.0 / float(self.cfg.simulation.get("sample_rate_hz", 10.0))
        self.fw_dir = tempfile.mkdtemp(prefix="aegis_live_fw_")

        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self.running = False

        self._active_attack_name: str | None = None
        self._pending_attack: str | None = "__none__"  # sentinel: no change pending
        self._sim_t = 0.0
        self._t0_wall = time.time()
        self._n_messages = 0
        self._n_decisions = 0
        # Rolling (wall_time, cumulative_messages) samples for live throughput.
        self._msg_samples: deque[tuple[float, int]] = deque(maxlen=512)
        # Cumulative simulated flight-path length (metres), summed from reported
        # positions — the same methodology the benchmark uses (_distance_m).
        self._distance_m = 0.0
        self._last_pos: tuple[float, float] | None = None
        # Live time-to-detect: sim time an attack was injected, and the elapsed
        # time to the FIRST alert after that injection (this session only).
        self._attack_injected_t: float | None = None
        self._ttd_pending = False
        self._last_ttd_s: float | None = None
        self._alerts: deque[dict] = deque(maxlen=200)
        self._latest_update: dict | None = None
        self._last_threat: dict = {}  # last DECISION's threat block (for status)
        self._run_seq = 0
        self._run_id = self._new_run_id()

        self._build()

    # -- lifecycle ---------------------------------------------------------- #

    def _new_run_id(self) -> str:
        """A unique run id per run, even across resets within the same second.

        A monotonic suffix keeps each run's hash chain independent (two resets
        in one wall-clock second would otherwise share a run_id and merge
        chains).
        """
        self._run_seq += 1
        return f"{time.strftime('live-%Y%m%d-%H%M%S')}-{self._run_seq}"

    def _build(self) -> None:
        self.pipeline = IDSPipeline(self.cfg, model_path=self.model_path, firmware_dir=self.fw_dir)
        self.source = SimulatedTelemetrySource(self.cfg, NoAttack(), seed=42)
        self._gen = self.source.stream()
        self.store = EventStore(self.db_path)
        self.store.start_run(self._run_id, label="live-demo")

    async def start(self) -> None:
        """Start the live loop on the current event loop (idempotent).

        Must be awaited from the event loop — ``asyncio.create_task`` needs a
        running loop, so the REST endpoints that call it are ``async`` (a sync
        endpoint runs in a threadpool worker with no loop and would raise).
        """
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the live loop and await the task's cancellation.

        Safe to call when not running. Cancelling *and awaiting* the old task
        before any restart prevents two ``_loop`` coroutines from ever driving
        the same pipeline concurrently (a restart race).
        """
        self.running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def reset(self) -> None:
        """Return the engine to a clean baseline (synchronous state reset).

        Task lifecycle is the caller's job: the REST reset endpoint awaits
        :meth:`stop` before this and :meth:`start` after, so this method does no
        async work and stays callable from tests / any thread. It reflashes the
        simulated firmware and clears all runtime state (see
        :meth:`IDSPipeline.reset`) and starts a fresh run id; historical event
        records from earlier runs are left untouched.
        """
        self.running = False
        self._active_attack_name = None
        self._pending_attack = "__none__"
        self._sim_t = 0.0
        self._n_messages = 0
        self._n_decisions = 0
        self._msg_samples.clear()
        self._distance_m = 0.0
        self._last_pos = None
        self._attack_injected_t = None
        self._ttd_pending = False
        self._last_ttd_s = None
        self._alerts.clear()
        self._latest_update = None
        self._last_threat = {}
        # Restore the simulated vehicle to a clean baseline: this reflashes the
        # firmware fixture to known-good AND clears extractor/detector/fusion
        # state (see IDSPipeline.reset).
        self.pipeline.reset()
        self._run_id = self._new_run_id()
        self.source = SimulatedTelemetrySource(self.cfg, NoAttack(), seed=42)
        self._gen = self.source.stream()
        self.store.start_run(self._run_id, label="live-demo")

    def set_attack(self, name: str | None) -> None:
        self._pending_attack = name or None

    # -- subscribers -------------------------------------------------------- #

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._subscribers.add(q)
        if self._latest_update:
            q.put_nowait(self._latest_update)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self, msg: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow client; drop this frame

    # -- attack swapping ---------------------------------------------------- #

    def _apply_pending_attack(self) -> None:
        if self._pending_attack == "__none__":
            return
        name = self._pending_attack
        self._pending_attack = "__none__"
        if not name or name in ("none", "benign"):
            self.source.attack = NoAttack()
            self._active_attack_name = None
            self._attack_injected_t = None
            self._ttd_pending = False
            return
        if name not in ATTACK_REGISTRY:
            return
        rng = np.random.default_rng(int(self._sim_t * 1000) & 0xFFFF)
        kwargs = {"firmware_dir": self.fw_dir} if name == "firmware_integrity" else {}
        atk = build_attack(name, self.cfg.attacks, rng, **kwargs)
        # Activate from *now* for a long window (until cleared).
        atk.start_s = self._sim_t
        atk.duration_s = _LIVE_DURATION_S
        self.source.attack = atk
        self._active_attack_name = name
        # Arm the live time-to-detect measurement: record the injection instant;
        # the first alert after this stamps the elapsed onset->detection time.
        self._attack_injected_t = self._sim_t
        self._ttd_pending = True

    # -- main loop ---------------------------------------------------------- #

    async def _loop(self) -> None:
        while self.running:
            t0 = time.perf_counter()
            self._apply_pending_attack()
            try:
                tick = next(self._gen)
            except StopIteration:
                self.source = SimulatedTelemetrySource(self.cfg, self.source.attack, seed=42)
                self._gen = self.source.stream()
                continue

            self._sim_t = tick.t
            self._n_messages += len(tick.messages)
            self._msg_samples.append((time.time(), self._n_messages))
            assessment = self.pipeline.process_tick(tick)
            self._accumulate_distance()
            update = self._make_update(tick, assessment)
            self._latest_update = update
            if assessment is not None:
                self._n_decisions += 1
                self._last_threat = update.get("threat", {})
                if assessment.is_alert:
                    row = self.store.log_event(assessment, self._run_id)
                    self._alerts.appendleft(self._alert_dict(assessment, row.get("id")))
                    # First alert after an injection -> stamp live time-to-detect.
                    if self._ttd_pending and self._attack_injected_t is not None:
                        self._last_ttd_s = round(assessment.t - self._attack_injected_t, 2)
                        self._ttd_pending = False
            await self._broadcast(update)

            await asyncio.sleep(max(0.0, self.dt - (time.perf_counter() - t0)))

    # -- runtime metrics ---------------------------------------------------- #

    def _accumulate_distance(self) -> None:
        """Add the current leg to the cumulative simulated flight-path length.

        Uses the reported (telemetry) position, matching the benchmark's
        ``_distance_m`` methodology — this is simulated *path length*, not
        geographic range or straight-line displacement.
        """
        s = self.pipeline.extractor.snapshot
        if s.lat is None or s.lon is None:
            return
        pos = (s.lat, s.lon)
        if self._last_pos is not None:
            self._distance_m += haversine_m(
                self._last_pos[0], self._last_pos[1], pos[0], pos[1]
            )
        self._last_pos = pos

    def _throughput(self) -> float:
        """Current live throughput (msg/s) over a rolling wall-clock window.

        Falls back to the full available sample span when the window has not yet
        filled, and to 0.0 only when there is genuinely no interval to divide by.
        """
        samples = self._msg_samples
        if len(samples) < 2:
            return 0.0
        now = time.time()
        windowed = [(t, n) for (t, n) in samples if now - t <= _THROUGHPUT_WINDOW_S]
        span = windowed if len(windowed) >= 2 else list(samples)
        (t0, n0), (t1, n1) = span[0], span[-1]
        dt = t1 - t0
        return round((n1 - n0) / dt, 1) if dt > 0 else 0.0

    # -- serialisation ------------------------------------------------------ #

    def _make_update(self, tick, assessment) -> dict:
        msg = {
            "type": "update",
            "sim": True,
            "t": round(tick.t, 2),
            "telemetry": self.pipeline._telemetry_dict(),
            "attack_active": self._active_attack_name,
            "distance_m": round(self._distance_m, 1),
        }
        if assessment is not None:
            msg["threat"] = {
                "threat": assessment.threat,
                "threat_score": assessment.threat_score,
                "severity": assessment.severity.value,
                "attack_type": assessment.attack_type.value,
                "confidence": assessment.confidence,
                "evidence": assessment.evidence,
                "detector_scores": assessment.detector_scores,
                "contributing_detectors": assessment.contributing_detectors,
                "integrity_status": assessment.integrity_status.value,
                "latency_ms": round(assessment.latency_ms, 3),
                "is_alert": assessment.is_alert,
            }
        return msg

    def _alert_dict(self, a, event_id) -> dict:
        return {
            "id": event_id,
            "t": round(a.t, 2),
            "attack_type": a.attack_type.value,
            "severity": a.severity.value,
            "threat_score": a.threat_score,
            "confidence": a.confidence,
            "evidence": a.evidence,
            "integrity_status": a.integrity_status.value,
            "latency_ms": round(a.latency_ms, 3),
        }

    # -- status snapshots --------------------------------------------------- #

    def status(self) -> dict:
        thr = self._last_threat
        return {
            "running": self.running,
            "sim": True,
            "sim_time_s": round(self._sim_t, 1),
            "uptime_s": round(time.time() - self._t0_wall, 1),
            "active_attack": self._active_attack_name,
            "ml_available": self.pipeline.ml_available,
            "threat": thr.get("threat", False),
            "severity": thr.get("severity", "NORMAL"),
            "attack_type": thr.get("attack_type", "BENIGN"),
            "threat_score": thr.get("threat_score", 0.0),
            "integrity_status": thr.get("integrity_status", IntegrityStatus.VALID.value),
            "distance_m": round(self._distance_m, 1),
            "run_id": self._run_id,
        }

    def metrics(self) -> dict:
        cs = self.store.verify_chain(self._run_id)
        return {
            "messages_processed": self._n_messages,
            "decisions": self._n_decisions,
            "alerts": len(self._alerts),
            "throughput_msgs_per_s": self._throughput(),
            # Compute cost of one fused decision (NOT attack-onset latency).
            "decision_compute_ms": self._last_threat.get("latency_ms"),
            "last_latency_ms": self._last_threat.get("latency_ms"),  # legacy alias
            # Attack-onset -> first-detection for the current session (or null).
            "time_to_detect_s": self._last_ttd_s,
            "distance_m": round(self._distance_m, 1),
            "event_log": {"count": cs.length, "chain_ok": cs.ok},
            "ml_available": self.pipeline.ml_available,
        }

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        return list(self._alerts)[:limit]
