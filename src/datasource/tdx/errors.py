from typing import Any

from src.datasource.tdx.market_normalization import normalize_symbol


class TdxNativeError(Exception):
    def __init__(self, native: dict[str, Any]) -> None:
        native_error_id = str(native.get("ErrorId", "UNKNOWN"))
        native_message = str(native.get("Error") or native.get("Message") or "TDX native error")
        super().__init__(native_message)
        self.code = "TDX_NATIVE_ERROR"
        self.message = native_message
        self.retryable = False
        self.details = {
            "nativeErrorId": native_error_id,
            "native": native,
        }


class TdxSymbolNotFoundError(Exception):
    def __init__(self, *, symbol: str, native: Any) -> None:
        normalized_symbol = normalize_symbol(symbol)
        message = f"TDX native response does not contain requested symbol {normalized_symbol}"
        super().__init__(message)
        self.code = "TDX_SYMBOL_NOT_FOUND"
        self.message = message
        self.retryable = False
        self.details = {
            "symbol": normalized_symbol,
            "native": native,
        }
