"""Dex office tour guide — semi-automatic tour orchestration.

See README.md. The hardware-control layer reuses Dex_Elevator's interface-first
design: guide/hardware defines the abstractions, the sim implementations let the
whole flow run without a robot, and the real adapters wire into Dex_Elevator's
core/robot/realman.py and core/hand/linkerhand.py.
"""
__version__ = "0.1.0"
