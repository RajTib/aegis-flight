"""Download + provenance bookkeeping for external datasets.

Every file we analyse is recorded in a JSON manifest with its source URL, byte
size, SHA-256 and retrieval time, so an external result can always be traced to
the exact bytes it was computed from. Raw files live under
``data/external/raw/`` (gitignored); manifests are small and committed.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = "aegisflight-research/0.1 (defensive UAV IDS research; contact via repo)"


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class FileRecord:
    url: str
    path: str  # repo-relative, forward slashes
    bytes: int
    sha256: str
    retrieved_utc: str


def download(url: str, dest: str | Path, timeout: float = 600.0, retries: int = 3) -> FileRecord:
    """Stream ``url`` to ``dest`` (skips the download if ``dest`` already exists)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size == 0:
        tmp = dest.with_suffix(dest.suffix + ".part")
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as r, tmp.open("wb") as fh:
                    while True:
                        buf = r.read(1 << 20)
                        if not buf:
                            break
                        fh.write(buf)
                tmp.replace(dest)
                last_err = None
                break
            except Exception as e:  # noqa: BLE001 - network errors are retried then re-raised
                last_err = e
                time.sleep(2.0 * (attempt + 1))
        if last_err is not None:
            raise last_err
    return FileRecord(
        url=url,
        path=dest.as_posix(),
        bytes=dest.stat().st_size,
        sha256=sha256_file(dest),
        retrieved_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def write_manifest(path: str | Path, dataset: dict, files: list[FileRecord],
                   extra: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"dataset": dataset, "files": [asdict(f) for f in files], **(extra or {})}
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def read_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
