"""TDX 实时行情 WebSocket 路由.

为 NestJS 后端提供实时行情推送的 WebSocket 接口.
对应 TDX SDK: tqcenter.tq (subscribe_hq, unsubscribe_hq, get_market_snapshot)

使用 TDX 原生订阅模式:
    1. subscribe_hq(stock_list, callback) - 注册回调，股票数据变化时触发
    2. 回调中调用 get_market_snapshot(code) - 拉取完整数据
    3. 通过 WebSocket 广播 - 推送给客户端

消息协议:
    客户端发送:
    - {"type": "ping"}                           心跳检测
    - {"type": "subscribe", "stocks": [...]}      订阅股票列表 (最多100只)
    - {"type": "unsubscribe", "stocks": [...]}    取消订阅

    服务端响应:
    - {"type": "pong"}                           心跳响应
    - {"type": "subscribed", "stocks": [...]}     订阅成功
    - {"type": "unsubscribed", "stocks": [...]}   取消订阅成功
    - {"type": "quote", "data": {...}}            实时行情数据
    - {"type": "error", "message": "..."}          错误信息

订阅限制:
    - TDX SDK 的 subscribe_hq 最多支持 100 只股票
    - 超过限制会返回错误
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import tdx.main
from src.ws.protocol import WSMessage

router = APIRouter()

# TDX 订阅限制：最多100只股票
TDX_MAX_SUBSCRIPTION = 100


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main as tdx_main
    return tdx_main.tdx_adapter


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """实时行情 WebSocket 端点 (TDX 原生模式).

    使用 TDX 的 subscribe_hq + get_market_snapshot 模式:
    1. 客户端发送订阅请求
    2. 验证股票数量不超过100只 (TDX SDK限制)
    3. 调用 adapter.subscribe_hq(stocks, callback) 注册回调
    4. 回调触发时，通过 asyncio.Queue 桥接到异步
    5. 异步任务调用 get_market_snapshot(code) 拉取数据
    6. 通过 WebSocket 广播数据

    对应 TDX SDK:
        - tq.subscribe_hq(stock_list, callback) - 注册订阅回调
        - tq.get_market_snapshot(stock_code, field_list) - 拉取行情快照
        - tq.unsubscribe_hq(stock_list) - 取消订阅

    Args:
        websocket: WebSocket 连接实例
        client_id: 客户端标识符

    Examples:
        连接: ws://localhost:9001/ws/quote/nestjs-instance-1
        心跳: {"type": "ping"}
        订阅: {"type": "subscribe", "stocks": ["600519.SH", "000001.SZ"]}
    """
    await websocket.accept()
    await tdx.main.ws_manager.connect(websocket, client_id)

    adapter = _get_adapter()
    if not adapter:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Adapter not initialized"
        }))
        await websocket.close()
        return

    # 用于桥接同步回调到异步的队列
    quote_queue: asyncio.Queue[str] = asyncio.Queue()

    # 订阅的股票集合
    subscribed_stocks: set[str] = set()

    # TDX SDK 回调函数 (在 SDK 线程中同步调用)
    def on_quote_update(data: dict[str, Any]) -> None:
        """TDX SDK 行情回调.

        当订阅的股票数据变化时，TDX SDK 会调用此函数.
        将股票代码放入队列，由异步任务处理.

        Args:
            data: SDK 回调数据，格式如 {"Code": "600519.SH", "ErrorId": "0"}
        """
        stock_code = data.get("Code", "")
        if stock_code:
            try:
                # 使用 call_soon_threadsafe 将数据放入异步队列
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(quote_queue.put_nowait, stock_code)
            except Exception:
                pass

    # 异步消费者任务：处理队列中的股票代码，拉取完整数据
    async def quote_consumer():
        """从队列获取股票代码，拉取行情数据并广播."""
        while True:
            try:
                stock_code = await quote_queue.get()
                if stock_code is None:  # 退出信号
                    break

                # 拉取完整行情快照
                snapshot = await adapter.get_market_snapshot(stock_code, [])

                # 构造消息并广播
                quote_msg = WSMessage(
                    type="quote",
                    data={
                        "stock_code": stock_code,
                        "snapshot": snapshot
                    }
                )

                # 发送给当前连接
                try:
                    await websocket.send_text(quote_msg.to_json())
                except Exception:
                    break

                quote_queue.task_done()

            except Exception:
                pass

    # 启动消费者任务
    consumer_task = asyncio.create_task(quote_consumer())

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "ping":
                # 心跳响应
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "subscribe":
                # 订阅股票
                stocks = message.get("stocks", [])

                # 验证股票数量
                if len(stocks) > TDX_MAX_SUBSCRIPTION:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Cannot subscribe to more than {TDX_MAX_SUBSCRIPTION} stocks"
                    }))
                    continue

                # 调用 TDX SDK 订阅
                try:
                    await adapter.subscribe_hq(stocks, on_quote_update)
                    subscribed_stocks.update(stocks)
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "stocks": stocks,
                        "message": f"Subscribed to {len(stocks)} stocks"
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Subscription failed: {str(e)}"
                    }))

            elif msg_type == "unsubscribe":
                # 取消订阅
                stocks = message.get("stocks", [])
                try:
                    await adapter.unsubscribe_hq(stocks)
                    for stock in stocks:
                        subscribed_stocks.discard(stock)
                    await websocket.send_text(json.dumps({
                        "type": "unsubscribed",
                        "stocks": stocks
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unsubscription failed: {str(e)}"
                    }))

            elif msg_type == "error":
                # 客户端错误
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": str(e)
            }))
        except Exception:
            pass

    finally:
        # 清理：取消所有订阅
        if subscribed_stocks and adapter:
            try:
                await adapter.unsubscribe_hq(list(subscribed_stocks))
            except Exception:
                pass

        # 停止消费者任务
        quote_queue.put_nowait(None)
        try:
            await asyncio.wait_for(consumer_task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        await tdx.main.ws_manager.disconnect(client_id)
