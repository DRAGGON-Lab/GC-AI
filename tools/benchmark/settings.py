"""Frozen deployment/evaluation semantics, including float32 comparison behavior."""

import struct

OPERATING_THRESHOLD = 0.7
# NumPy compares float32 detector arrays to a scalar cast to the array dtype.
EFFECTIVE_OPERATING_THRESHOLD = struct.unpack("f", struct.pack("f", OPERATING_THRESHOLD))[0]
