from src.datasource.qmt.local_dat import QmtLocalDatReader


class QmtMarketOperations:
    def __init__(self, local_dat_reader: QmtLocalDatReader) -> None:
        self.local_dat_reader = local_dat_reader

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
        _ = (dividend_type, fill_data)
        return self.local_dat_reader.read_market_data(
            stock_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
            fields=fields,
            include_raw=include_raw,
        )

    async def collect_recent_bars(
        self,
        stock_list: list[str],
        period: str,
        count: int,
    ) -> dict[str, object]:
        return await self.get_bars(
            stock_list,
            period=period,
            start_time=None,
            end_time=None,
            count=count,
        )
