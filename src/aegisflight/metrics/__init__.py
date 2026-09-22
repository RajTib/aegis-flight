"""Detection-quality and resource metrics computed from real runs."""

from .resources import ResourceSampler
from .scoring import BinaryStats, ClassScore, Evaluation, evaluate

__all__ = ["evaluate", "Evaluation", "BinaryStats", "ClassScore", "ResourceSampler"]
