"""MOTIONIQ. Coordinates are estimates, never a calibrated factory frame."""

__version__ = "0.1.0"


import os

# Keep existing private installations configured during the product rename.
for _name, _value in tuple(os.environ.items()):
    if _name.startswith("EGOHAND_"):
        os.environ.setdefault("MOTIONIQ_" + _name[len("EGOHAND_"):], _value)
