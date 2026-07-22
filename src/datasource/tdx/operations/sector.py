from typing import Any

from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.native import native_items
from src.datasource.tdx.normalizers.sector import normalize_sector_item, normalize_sector_members


class TdxSectorOperations:
    def __init__(self, client: TdxHttpClient) -> None:
        self.client = client

    async def get_sector_list(self, list_type: int = 0) -> list[dict[str, Any]]:
        native = await self.client.call("get_sector_list", {"list_type": list_type})
        return [normalize_sector_item(item) for item in native_items(native)]

    async def get_sector_members(self, sector: str) -> list[str]:
        native = await self.client.call(
            "get_stock_list_in_sector",
            {
                "block_code": sector,
            },
        )
        return normalize_sector_members(native)
