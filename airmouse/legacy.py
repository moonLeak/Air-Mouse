"""
Legacy entrypoint preserved for compatibility.

The original monolithic implementation has been decomposed into dedicated
modules. Importing this module now raises an explicit error to make sure any
lingering references are updated to the new structure.
"""

raise RuntimeError(
    "airmouse.legacy has been retired. "
    "Run `python -m airmouse` to use the modular AirMouseApplication."
)
