from src.datasource.qmt.local_dat import QmtLocalDatReader
from src.datasource.qmt.operations.market import QmtMarketOperations


class QmtDatasourceProvider:
    def __init__(self, *, local_dat_reader: QmtLocalDatReader | None = None) -> None:
        self.local_dat_reader = local_dat_reader or QmtLocalDatReader.from_settings()
        self._market = QmtMarketOperations(self.local_dat_reader)

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
        )

    async def collect_recent_bars(
        self,
        stock_list: list[str],
        period: str,
        count: int,
    ) -> dict[str, object]:
        return await self._market.collect_recent_bars(stock_list, period, count)
