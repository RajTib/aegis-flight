"""Simultaneous attacks: several :class:`Attack` objects applied together.

Each hook is chained through the components in order (value attacks compose on
the state, stream attacks compose on the packet list), so a combination is
exactly "attack A and attack B at once" with no new perturbation logic.

Ground truth is **multi-label**: :meth:`labels` returns every active
component's class. :meth:`label` (single-label, used by the binary benchmark)
returns the first active component in list order, which the caller controls.
"""

from __future__ import annotations

import numpy as np

from ..core.enums import AttackType, IntegrityStatus
from .base import Attack


class CompositeAttack(Attack):
    def __init__(self, components: list[Attack], rng: np.random.Generator | None = None) -> None:
        if not components:
            raise ValueError("CompositeAttack needs at least one component")
        super().__init__({}, rng or np.random.default_rng(0))
        self.components = list(components)
        self.attack_type = components[0].attack_type
        wins = [c.window() for c in components]
        self.start_s = min(w[0] for w in wins)
        self.duration_s = max(w[1] for w in wins) - self.start_s

    def active(self, t: float) -> bool:
        return any(c.active(t) for c in self.components)

    def label(self, t: float) -> AttackType:
        for c in self.components:
            lab = c.label(t)
            if lab is not AttackType.BENIGN:
                return lab
        return AttackType.BENIGN

    def labels(self, t: float) -> frozenset[AttackType]:
        return frozenset().union(*(c.labels(t) for c in self.components))

    def window(self) -> tuple[float, float]:
        return self.start_s, self.start_s + self.duration_s

    def before_encode(self, t, tick, encoder):
        for c in self.components:
            c.before_encode(t, tick, encoder)

    def perturb_state(self, t, state):
        for c in self.components:
            state = c.perturb_state(t, state)
        return state

    def perturb_packets(self, t, packets, ctx):
        for c in self.components:
            packets = c.perturb_packets(t, packets, ctx)
        return packets

    def integrity_status(self, t: float) -> IntegrityStatus:
        statuses = [c.integrity_status(t) for c in self.components]
        return IntegrityStatus.INVALID if IntegrityStatus.INVALID in statuses else IntegrityStatus.VALID
