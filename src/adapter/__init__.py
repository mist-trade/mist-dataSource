"""Adapter factory for creating market data adapters."""

from src.adapter.base import MarketDataAdapter, QmtDataAdapter, TdxDataAdapter
from src.adapter.mock.qmt_mock import QMTMockAdapter
from src.adapter.mock.tdx_mock import TDXMockAdapter
from src.core.config import settings
from src.core.exceptions import AdapterError


def create_tdx_adapter() -> TdxDataAdapter:
    """根据运行环境创建 TDX 适配器.

    Returns:
        TDXAdapter 实例（生产环境）或 TDXMockAdapter（开发环境）

    Examples:
        >>> adapter = create_tdx_adapter()
        >>> await adapter.initialize()
        >>> stocks = await adapter.get_stock_list()
    """
    if settings.is_production:
        from src.adapter.tdx.client import TDXAdapter

        return TDXAdapter()
    else:
        return TDXMockAdapter()


def create_qmt_adapter(path: str = "", account_id: str = "") -> QmtDataAdapter:
    """根据运行环境创建 QMT 适配器.

    Args:
        path: 保留参数，生产环境不再使用本地 SDK 路径
        account_id: 保留参数，生产环境不再使用账户直连

    Returns:
        QMTMockAdapter（开发环境）。生产 QMT 需走 full-QMT bridge。

    Examples:
        >>> adapter = create_qmt_adapter(
        ...     path="",
        ...     account_id="12345678"
        ... )
        >>> await adapter.initialize()
    """
    if settings.is_production:
        raise AdapterError(
            "Production QMT adapter is disabled until full-QMT bridge spike "
            "evidence enables the provider."
        )
    else:
        return QMTMockAdapter(path, account_id)


__all__ = [
    "MarketDataAdapter",
    "QmtDataAdapter",
    "TdxDataAdapter",
    "create_tdx_adapter",
    "create_qmt_adapter",
]
