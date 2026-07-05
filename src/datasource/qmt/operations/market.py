from src.datasource.qmt.local_dat import QmtLocalDatReader
from src.datasource.tdx_models import TdxBar


class QmtMarketOperations:
    def __init__(self, local_dat_reader: QmtLocalDatReader) -> None:
        self.local_dat_reader = local_dat_reader

    async def get_bars(
        self,
        symbols: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
        fields: list[str] | None = None,
        dividend_type: str | None = None,
        fill_data: bool | None = None,
    ) -> list[TdxBar]:
        _ = (fields, dividend_type, fill_data)
        return self.local_dat_reader.read_bars(
            symbols,
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
        )

    async def collect_recent_bars(
        self,
        symbols: list[str],
        period: str,
        count: int,
    ) -> list[TdxBar]:
        return await self.get_bars(
            symbols,
            period=period,
            start_time=None,
            end_time=None,
            count=count,
        )
