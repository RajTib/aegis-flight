"""MAVLink telemetry log (``.tlog``) -> AegisFlight ``TelemetryTick`` replay.

A ``.tlog`` is what a ground station records off the real radio link: every
MAVLink frame with the GCS receive timestamp. Unlike a ULog it carries the
*link* itself (message mix, rates, inter-arrival timing, sequence numbers,
source ids), so the **full** AegisFlight pipeline -- protocol, physics, ML and
fusion -- can be replayed on it unchanged.

Ground-station clocks are not monotonic in practice (one ALFA log jumps nine
days mid-file), so :func:`segments` splits a log wherever the receive clock
jumps backwards or stalls for longer than ``max_gap_s``; each segment is
replayed through a *fresh* pipeline, exactly as a restarted IDS would see it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from ..core.enums import AttackType
from ..core.types import MessageEnvelope
from ..sources.stream import TelemetryTick


def iter_tlog(path: str | Path, dialect: str = "ardupilotmega") -> Iterator[MessageEnvelope]:
    """Yield decoded envelopes; ``recv_time`` is the absolute (UNIX) GCS timestamp."""
    from pymavlink import mavutil

    conn = mavutil.mavlink_connection(str(path), dialect=dialect, robust_parsing=True)
    while True:
        msg = conn.recv_match(blocking=False)
        if msg is None:
            break
        name = msg.get_type()
        if name == "BAD_DATA":
            continue
        fields = msg.to_dict()
        fields.pop("mavpackettype", None)
        try:
            blen = len(msg.get_msgbuf())
        except Exception:  # noqa: BLE001 - some decoded msgs have no buffer
            blen = 0
        yield MessageEnvelope(
            recv_time=float(getattr(msg, "_timestamp", 0.0)), sysid=msg.get_srcSystem(),
            compid=msg.get_srcComponent(), msgid=msg.get_msgId(), msgname=name,
            seq=msg.get_seq(), signed=bool(getattr(msg, "get_signed", lambda: False)()),
            byte_len=blen, fields=fields)


def segments(envs: Iterator[MessageEnvelope], max_gap_s: float = 30.0,
             max_backstep_s: float = 1.0) -> list[tuple[float, list[MessageEnvelope]]]:
    """Split on clock jumps; return ``[(segment_t0_unix, envelopes_rebased_to_0), ...]``."""
    out: list[tuple[float, list[MessageEnvelope]]] = []
    cur: list[MessageEnvelope] = []
    t0 = prev = None
    for e in envs:
        ts = e.recv_time
        if prev is not None and (ts - prev > max_gap_s or prev - ts > max_backstep_s):
            out.append((t0, cur))
            cur, t0 = [], None
        if t0 is None:
            t0 = ts
        # tolerate tiny backward steps (GCS reordering) by clamping to monotonic
        rt = max(ts - t0, cur[-1].recv_time if cur else 0.0)
        e.recv_time = rt
        cur.append(e)
        prev = ts
    if cur:
        out.append((t0, cur))
    return out


def tlog_ticks(envs: list[MessageEnvelope], sample_rate_hz: float = 10.0,
               label_fn: Callable[[float], AttackType] | None = None) -> Iterator[TelemetryTick]:
    """Bucket re-based envelopes into fixed-rate ticks for ``IDSPipeline.process_tick``.

    Tick ``k`` (time ``k*dt``) delivers every frame received in ``((k-1)*dt, k*dt]``,
    so no frame is ever processed before its receive time.
    """
    dt = 1.0 / sample_rate_hz
    label_fn = label_fn or (lambda _t: AttackType.BENIGN)
    bucket: list[MessageEnvelope] = []
    k = 0
    for env in envs:
        while env.recv_time > k * dt:
            t = k * dt
            yield TelemetryTick(t=t, tick=k, messages=bucket, label=label_fn(t))
            bucket = []
            k += 1
        bucket.append(env)
    yield TelemetryTick(t=k * dt, tick=k, messages=bucket, label=label_fn(k * dt))
