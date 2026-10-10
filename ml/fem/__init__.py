"""Independent, opt-in synthetic steady-conduction reference.

No estimator, transport, database or frontend import belongs in this package.
"""

from .solver import FEMError, Mesh, Solution, rectangle_mesh, solve_steady

__all__ = ["FEMError", "Mesh", "Solution", "rectangle_mesh", "solve_steady"]
