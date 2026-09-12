"""Measuring whether a change helped.

Without this, every prompt edit, rubric tweak and model swap is a guess. The suite is
small and hand-labelled rather than large and automatic, because the thing being
measured is agreement with human judgement and there is no way to get that cheaply.
"""

from .fixtures import CASES, Case
from .run import Report, run_suite

__all__ = ["CASES", "Case", "Report", "run_suite"]
