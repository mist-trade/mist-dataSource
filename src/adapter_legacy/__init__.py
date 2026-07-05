"""Adapter factory for creating market data adapters."""

from src.adapter_legacy.base import TdxLegacyAdapterBase, TdxLegacyAdapterProtocol
from src.adapter_legacy.mock.tdx_mock import TdxLegacyMockAdapter
from src.core.config import settings


def create_tdx_legacy_adapter() -> TdxLegacyAdapterProtocol:
    """根据运行环境创建 TDX 适配器.

    Returns:
        TdxLegacyAdapter 实例（生产环境）或 TdxLegacyMockAdapter（开发环境）

    Examples:
        >>> adapter = create_tdx_legacy_adapter()
        >>> await adapter.initialize()
        >>> stocks = await adapter.get_stock_list()
    """
    if settings.is_production:
        from src.adapter_legacy.tdx.client import TdxLegacyAdapter

        return TdxLegacyAdapter()
    else:
        return TdxLegacyMockAdapter()


__all__ = [
    "TdxLegacyAdapterBase",
    "TdxLegacyAdapterProtocol",
    "create_tdx_legacy_adapter",
]
