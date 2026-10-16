"""Tools for writing a scenario: scaffolding a new package and checking one.

Backs ``glossogen new-scenario`` and ``glossogen validate``. The scenario contract
itself (``scenario_protocol``, ``scenario_base``, the loader) stays at the package
root, since scenarios in other distributions import it.
"""
