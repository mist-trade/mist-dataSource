"""QMT provider-symbol rules for callback transport."""

import re

QMT_SYMBOL_PATTERN = re.compile(r"^(?:\d{6}\.(?:SH|SZ|BJ)|\d{5,6}\.HK)$")
