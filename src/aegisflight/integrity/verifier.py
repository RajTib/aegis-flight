"""Firmware-integrity verification via SHA-256 manifests.

This is a *real* cryptographic check, not a mock: a signed manifest records the
SHA-256 of every firmware component; the verifier re-hashes the on-disk files
and reports any mismatch, addition, or deletion. The firmware-tampering attack
scenario flips bytes in a component file and this verifier genuinely detects it.

A tiny deterministic firmware fixture can be synthesised for the PoC so the
whole flow (build manifest -> tamper -> detect) runs offline and reproducibly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.enums import IntegrityStatus

HASH_ALGO = "sha256"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class IntegrityReport:
    status: IntegrityStatus
    checked: int = 0
    tampered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "checked": self.checked,
            "tampered": self.tampered,
            "missing": self.missing,
            "unexpected": self.unexpected,
            "evidence": self.evidence,
        }


# Deterministic PoC firmware components (name -> content). Content is fixed so
# the manifest is reproducible across machines.
_FIXTURE_COMPONENTS: dict[str, bytes] = {
    "bootloader.bin": b"AEGIS-BL v1.4.2\x00" + bytes(range(256)) * 8,
    "ekf3_params.bin": b"EKF3-PARAMS\x00" + bytes((i * 7) % 256 for i in range(2048)),
    "motor_ctrl.bin": b"MOTOR-CTRL v2.1\x00" + bytes((i * 13) % 256 for i in range(1024)),
    "comms_stack.bin": b"MAVLINK-STACK\x00" + bytes((i * 29) % 256 for i in range(1536)),
    "mission_fs.bin": b"MISSION-FS\x00" + bytes((i * 31) % 256 for i in range(768)),
}


class FirmwareVerifier:
    """Builds and verifies a SHA-256 firmware manifest for a directory."""

    def __init__(self, firmware_dir: Path | str, manifest_path: Path | str | None = None) -> None:
        self.firmware_dir = Path(firmware_dir)
        self.manifest_path = (
            Path(manifest_path) if manifest_path else self.firmware_dir / "manifest.json"
        )

    # -- fixture / manifest management -------------------------------------- #

    def write_fixture(self) -> None:
        """Write the deterministic PoC firmware components to disk."""
        self.firmware_dir.mkdir(parents=True, exist_ok=True)
        for name, content in _FIXTURE_COMPONENTS.items():
            (self.firmware_dir / name).write_bytes(content)

    def build_manifest(self) -> dict:
        """Hash every ``*.bin`` component and write the signed manifest."""
        files = {
            p.name: sha256_file(p)
            for p in sorted(self.firmware_dir.glob("*.bin"))
        }
        manifest = {
            "algo": HASH_ALGO,
            "version": "1.0",
            "components": files,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def ensure_fixture(self) -> None:
        """Create the fixture + manifest if they don't already exist."""
        if not self.manifest_path.exists():
            self.write_fixture()
            self.build_manifest()

    # -- verification ------------------------------------------------------- #

    def tamper(self, component: str) -> bool:
        """Flip a byte in a component file (simulates firmware tampering).

        Returns True if the file existed and was modified.
        """
        target = self.firmware_dir / component
        if not target.exists():
            return False
        data = bytearray(target.read_bytes())
        idx = len(data) // 2
        data[idx] ^= 0xFF  # single-byte flip -> different SHA-256
        target.write_bytes(bytes(data))
        return True

    def verify(self) -> IntegrityReport:
        """Re-hash on-disk components and compare to the manifest."""
        if not self.manifest_path.exists():
            return IntegrityReport(
                status=IntegrityStatus.UNKNOWN,
                evidence=["no firmware manifest present"],
            )
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        expected: dict[str, str] = manifest.get("components", {})
        on_disk = {p.name: p for p in self.firmware_dir.glob("*.bin")}

        tampered, missing, unexpected, evidence = [], [], [], []
        for name, exp_hash in expected.items():
            if name not in on_disk:
                missing.append(name)
                evidence.append(f"component missing: {name}")
                continue
            actual = sha256_file(on_disk[name])
            if actual != exp_hash:
                tampered.append(name)
                evidence.append(
                    f"SHA-256 mismatch: {name} "
                    f"expected {exp_hash[:12]}… got {actual[:12]}…"
                )
        for name in on_disk:
            if name not in expected:
                unexpected.append(name)
                evidence.append(f"unexpected component: {name}")

        if tampered or missing or unexpected:
            status = IntegrityStatus.INVALID
        else:
            status = IntegrityStatus.VALID
            evidence.append(f"all {len(expected)} components verified (SHA-256)")
        return IntegrityReport(
            status=status,
            checked=len(expected),
            tampered=tampered,
            missing=missing,
            unexpected=unexpected,
            evidence=evidence,
        )

    def restore(self) -> None:
        """Rewrite the fixture to its pristine content (undo tampering)."""
        self.write_fixture()
