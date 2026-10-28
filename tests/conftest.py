"""Pytest configuration and environment initialization."""

from __future__ import annotations

import os

# Ensure OpenBLAS thread slots are not exhausted on Windows
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
