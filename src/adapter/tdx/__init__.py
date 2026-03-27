"""TDX adapter module for TongDaXin integration.

This module requires the tqcenter SDK which is only available on Windows.
On macOS, the mock adapter will be used instead.
"""

from src.adapter.tdx.client import TDXAdapter

__all__ = ["TDXAdapter"]
