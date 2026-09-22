"""Tamper-evident event logging (SQLite + SHA-256 hash chain)."""

from .store import ChainStatus, EventStore

__all__ = ["EventStore", "ChainStatus"]
