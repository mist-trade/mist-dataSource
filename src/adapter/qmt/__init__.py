"""QMT adapter module for miniQMT integration.

This module requires the xtquant SDK which is only available on Windows.
On macOS, the mock adapter will be used instead.
"""

from src.adapter.qmt.client import QMTAdapter

__all__ = ["QMTAdapter"]
