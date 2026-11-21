"""Tank-AI simulator package.

Phase 1 scope is read-only monitoring: the simulator produces signal values so
firmware, cloud and dashboard work can be developed without hardware. It never
simulates an output to the hardwired safety chain.

Story P1-02 builds the simulator proper on top of this package. CHORE-01 added
only what the CI contract needs: one real module and its tests, so the 80%
coverage gate measures something.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
