# coding: gbk
"""MistVisualBridge.py - QMT (ThinkTrader) 通用绘图指令极简哑执行器

此脚本直接作为 QMT 客户端的「主图技术指标」加载。
零业务逻辑、零缠论计算、零指令生成，仅负责：
1. 在 handlebar 中向本地 Mist 视觉引擎请求当前股票与周期的绘图指令集；
2. 将指令（line / band / text / icon）直接映射并调用 ContextInfo.paint() 进行原生硬件加速绘制。
"""

import json
import urllib.error
import urllib.request

# QMT 周期代码到 Mist 分钟数的映射
PERIOD_MAP = {
    "1m": 1,
    "1min": 1,
    "5m": 5,
    "5min": 5,
    "15m": 15,
    "15min": 15,
    "30m": 30,
    "30min": 30,
    "60m": 60,
    "60min": 60,
    "1d": 1440,
    "daily": 1440,
    "1w": 10080,
    "weekly": 10080,
}


def init(ContextInfo):
    """指标初始化"""
    pass


def handlebar(ContextInfo):
    """K线刷新驱动事件：向 Mist 后端请求通用绘图指令并调用 paint() 渲染"""
    # 仅在最新一根 K 线时执行全量渲染映射，避免逐根重复发 HTTP 请求
    if not ContextInfo.is_last_bar():
        return

    raw_symbol = getattr(ContextInfo, "stockcode", "")
    if not raw_symbol:
        return

    # 去除交易所前缀后缀（如 000001.SZ -> 000001）
    stock_code = raw_symbol.split(".")[0]
    period_str = str(getattr(ContextInfo, "period", "5m")).lower()
    period_minutes = PERIOD_MAP.get(period_str, 5)

    url = (
        f"http://127.0.0.1:8001/v1/visual/commands"
        f"?code={stock_code}&period={period_minutes}&source=qmt&layers=chan,backtest"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mist-QMT-VisualBridge/1.0"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status != 200:
                return
            body = resp.read().decode("utf-8")
            payload = json.loads(body)
            data = payload.get("data", {})
            commands = data.get("commands", [])

            for cmd in commands:
                cmd_type = cmd.get("type")
                cmd_id = cmd.get("id", "item")
                color = cmd.get("color", "#FACC15")

                # 1. 绘制折线 (笔、线段、通道)
                if cmd_type == "line":
                    # 绘制起点到终点标线
                    start_price = cmd.get("startPrice")
                    end_price = cmd.get("endPrice")
                    if start_price is not None and end_price is not None:
                        ContextInfo.paint(
                            f"{cmd_id}_L",
                            end_price,
                            draw_type=0,  # 0: 折线
                            color=color,
                        )

                # 2. 绘制中枢区间带 (ZG/ZD)
                elif cmd_type == "band":
                    top = cmd.get("top")
                    bottom = cmd.get("bottom")
                    if top is not None and bottom is not None:
                        ContextInfo.paint(f"{cmd_id}_ZG", top, draw_type=0, color=color)
                        ContextInfo.paint(f"{cmd_id}_ZD", bottom, draw_type=0, color=color)

                # 3. 绘制买卖点文本与标记
                elif cmd_type == "text":
                    price = cmd.get("price")
                    label = cmd.get("text", "")
                    if price is not None:
                        ContextInfo.paint(
                            cmd_id,
                            price,
                            draw_type=3,  # 3: 文字
                            text=label,
                            color=color,
                        )

                # 4. 绘制图标
                elif cmd_type == "icon":
                    price = cmd.get("price")
                    if price is not None:
                        ContextInfo.paint(
                            cmd_id,
                            price,
                            draw_type=2,  # 2: 图标
                            color=color,
                        )
    except Exception:
        # 网络超时或异常时不阻塞 QMT 正常看盘
        pass
