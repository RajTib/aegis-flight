#!/usr/bin/env python
"""Download the public real-flight datasets used by the external validation.

Usage:
    python scripts/fetch_external_data.py --alfa
    python scripts/fetch_external_data.py --px4 40 --px4-seed 2026

Raw files go to ``data/external/raw/`` (gitignored). A provenance manifest
(URL, bytes, SHA-256, retrieval time, selection protocol) is written to
``data/external/manifests/`` and IS committed, so every external result is
traceable to exact bytes. Safe, read-only use of public data.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from aegisflight.external import alfa, px4_review
from aegisflight.external.provenance import download, write_manifest

RAW = Path("data/external/raw")
MAN = Path("data/external/manifests")


def fetch_alfa() -> None:
    recs = []
    for name, url in alfa.FILES.items():
        print(f"ALFA: {name} …", flush=True)
        recs.append(download(url, RAW / "alfa" / name))
    tel = RAW / "alfa" / "telemetry.zip"
    out = RAW / "alfa" / "telemetry"
    if not out.exists():
        with zipfile.ZipFile(tel) as z:
            z.extractall(out)
    proc = RAW / "alfa" / "processed.zip"
    pout = RAW / "alfa" / "processed"
    if not pout.exists():
        with zipfile.ZipFile(proc) as z:
            z.extractall(pout)
    write_manifest(MAN / "alfa.json",
                   {"name": "ALFA", "source": alfa.FIGSHARE_ARTICLE, "license": alfa.LICENSE,
                    "citation": alfa.CITATION, "real_or_synthetic": "real flights"},
                   recs)
    print(f"ALFA manifest -> {MAN / 'alfa.json'}")


def fetch_px4(n: int, seed: int, protocol: str) -> None:
    sel = px4_review.PROTOCOLS[protocol]
    db_path = RAW / "px4_review" / "dbinfo.json"
    if not db_path.exists():
        print("PX4 Flight Review: fetching public dbinfo …", flush=True)
        px4_review.fetch_dbinfo(db_path)
    db = px4_review.load_dbinfo(db_path)
    picked, n_eligible = px4_review.select_logs(db, n, seed, sel)
    print(f"PX4: {len(db)} public logs, {n_eligible} eligible, sampling {len(picked)} (seed={seed})")
    recs, meta = [], []
    for e in picked:
        url = px4_review.DOWNLOAD_URL.format(log_id=e["log_id"])
        try:
            rec = download(url, RAW / "px4_review" / "ulg" / f"{e['log_id']}.ulg")
        except Exception as ex:  # noqa: BLE001 - record and continue
            print(f"  ! {e['log_id']}: {ex}")
            meta.append({"log_id": e["log_id"], "download_error": str(ex)})
            continue
        recs.append(rec)
        meta.append({k: e.get(k) for k in ("log_id", "log_date", "sys_hw", "mav_type", "duration_s",
                                          "rating", "ver_sw_release", "airframe_name", "wind_speed")})
        print(f"  ok {e['log_id']} {rec.bytes/1e6:.1f} MB", flush=True)
    manifest = MAN / f"px4_review_{protocol}.json"
    write_manifest(manifest,
                   {"name": "PX4 Flight Review public logs", "source": px4_review.DBINFO_URL,
                    "license": "public uploads; no dataset licence stated -- analysed locally, "
                               "raw logs not redistributed",
                    "real_or_synthetic": "uploaded flight logs (SITL excluded by selection; "
                                         "HITL excluded at load time)"},
                   recs,
                   extra={"selection": sel, "protocol": protocol, "seed": seed, "n_requested": n,
                          "n_public_logs": len(db), "n_eligible": n_eligible, "logs": meta})
    print(f"PX4 manifest -> {manifest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alfa", action="store_true")
    ap.add_argument("--px4", type=int, default=0, help="number of PX4 Flight Review logs")
    ap.add_argument("--px4-seed", type=int, default=2026)
    ap.add_argument("--px4-protocol", choices=sorted(px4_review.PROTOCOLS), default="v2")
    a = ap.parse_args()
    if a.alfa:
        fetch_alfa()
    if a.px4:
        fetch_px4(a.px4, a.px4_seed, a.px4_protocol)


if __name__ == "__main__":
    main()
