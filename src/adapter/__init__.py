"""Adapter factory for creating market data adapters."""

from src.adapter.base import MarketDataAdapter
from src.adapter.mock.qmt_mock import QMTMockAdapter
from src.adapter.mock.tdx_mock import TDXMockAdapter
from src.core.config import settings


def create_tdx_adapter() -> MarketDataAdapter:
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


def create_qmt_adapter(path: str = "", account_id: str = "") -> MarketDataAdapter:
    """根据运行环境创建 QMT 适配器.

    Args:
        path: QMT 客户端路径（仅生产环境需要）
        account_id: QMT 账户 ID（仅生产环境需要）

    Returns:
        QMTAdapter 实例（生产环境）或 QMTMockAdapter（开发环境）

    Examples:
        >>> adapter = create_qmt_adapter(
        ...     path="D:\\miniQMT",
        ...     account_id="12345678"
        ... )
        >>> await adapter.initialize()
    """
    if settings.is_production:
        if not path:
            path = settings.qmt.path
        if not account_id:
            account_id = settings.qmt.account_id

        from src.adapter.qmt.client import QMTAdapter

        return QMTAdapter(path, account_id)
    else:
        return QMTMockAdapter(path, account_id)


__all__ = ["MarketDataAdapter", "create_tdx_adapter", "create_qmt_adapter"]
