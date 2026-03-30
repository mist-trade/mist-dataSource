"""QMT 实时行情 WebSocket 路由.

为 NestJS 后端提供实时行情推送的 WebSocket 接口.
对应 QMT SDK: xtquant.xtdata (subscribe_quote, subscribe_whole_quote)

消息协议:
    客户端发送:
    - {"type": "ping"}                       心跳检测
    - {"type": "subscribe", "stocks": []}    订阅单股行情

    服务端响应:
    - {"type": "pong"}                       心跳响应
    - {"type": "subscribed", "stocks": []}   订阅确认
    - {"type": "quote", "data": {}}          行情推送
    - {"type": "error", "data": {"error": ""}} 错误信息
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from qmt.main import qmt_adapter, ws_manager
from src.ws.protocol import WSMessage

router = APIRouter()


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """实时行情 WebSocket 端点.

    NestJS 后端连接此端点以接收实时行情推送. 连接建立后保持长连接，
    通过 JSON 消息进行心跳检测和股票订阅管理.

    对应 QMT SDK:
        - xtdata.subscribe_quote(stock_code, period, callback)
        - xtdata.unsubscribe_quote(seq)

    Args:
        websocket: WebSocket 连接实例
        client_id: 客户端标识符，用于区分不同的 NestJS 后端实例

    Examples:
        连接: ws://localhost:9002/ws/quote/nestjs-instance-1
        心跳: {"type": "ping"}
        订阅: {"type": "subscribe", "stocks": ["000001.SZ", "600000.SH"]}
    """
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "subscribe":
                stocks = message.get("stocks", [])
                if not qmt_adapter:
                    await websocket.send_text(
                        json.dumps({"type": "error", "data": {"error": "Adapter not initialized"}})
                    )
                    continue

                await websocket.send_text(
                    json.dumps({
                        "type": "subscribed",
                        "stocks": stocks,
                        "message": f"Subscribed to {len(stocks)} stocks",
                    })
                )

                async for quote_data in qmt_adapter.subscribe_quote(stocks):
                    msg = WSMessage(type="quote", data=quote_data)
                    await ws_manager.broadcast(msg)

    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
    except Exception as e:
        await ws_manager.disconnect(client_id)
        try:
            error_msg = WSMessage(type="error", data={"error": str(e)})
            await websocket.send_text(error_msg.to_json())
        except Exception:
            pass
