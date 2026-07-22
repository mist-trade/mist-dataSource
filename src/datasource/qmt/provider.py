from src.datasource.qmt.bridge import QmtCommandGateway
from src.datasource.qmt.operations.market import QmtMarketOperations


class QmtDatasourceProvider:
    def __init__(self) -> None:
        self._market = QmtMarketOperations()

    async def get_bars(
        self,
        stock_list: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
        fields: list[str] | None = None,
        dividend_type: str | None = None,
        fill_data: bool | None = None,
        include_raw: bool = False,
        command_gateway: QmtCommandGateway | None = None,
        bridge_timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        return await self._market.get_bars(
            stock_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
            fields=fields,
            dividend_type=dividend_type,
            fill_data=fill_data,
            include_raw=include_raw,
            command_gateway=command_gateway,
            bridge_timeout_seconds=bridge_timeout_seconds,
        )

    async def collect_recent_bars(
        self,
        stock_list: list[str],
        period: str,
        count: int,
        *,
        command_gateway: QmtCommandGateway | None = None,
    ) -> dict[str, object]:
        return await self._market.collect_recent_bars(
            stock_list,
            period,
            count,
            command_gateway=command_gateway,
        )
