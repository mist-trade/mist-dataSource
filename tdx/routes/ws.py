"""TDX 实时行情 WebSocket 路由.

为 NestJS 后端提供实时行情推送的 WebSocket 接口.
对应 TDX SDK: tqcenter.tq (subscribe_hq, unsubscribe_hq)

消息协议:
    客户端发送:
    - {"type": "ping"}                    心跳检测
    - {"type": "subscribe", "stocks": []} 订阅股票列表

    服务端响应:
    - {"type": "pong"}                    心跳响应
    - {"type": "subscribed", "stocks": [], "message": ""} 订阅确认
    - {"type": "error", "data": {"error": ""}} 错误信息
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import tdx.main
from src.ws.protocol import WSMessage

router = APIRouter()


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """实时行情 WebSocket 端点.

    NestJS 后端连接此端点以接收实时行情推送. 连接建立后保持长连接，
    通过 JSON 消息进行心跳检测和股票订阅管理.

    对应 TDX SDK:
        - tq.subscribe_hq(stock_list, callback)
        - tq.unsubscribe_hq(stock_list)

    Args:
        websocket: WebSocket 连接实例
        client_id: 客户端标识符，用于区分不同的 NestJS 后端实例

    Examples:
        连接: ws://localhost:9001/ws/quote/nestjs-instance-1
        心跳: {"type": "ping"}
        订阅: {"type": "subscribe", "stocks": ["SH600519", "SZ000001"]}
    """
    await tdx.main.ws_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "subscribe":
                stocks = message.get("stocks", [])
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "subscribed",
                            "stocks": stocks,
                            "message": f"Subscribed to {len(stocks)} stocks",
                        }
                    )
                )

    except WebSocketDisconnect:
        await tdx.main.ws_manager.disconnect(client_id)
    except Exception as e:
        await tdx.main.ws_manager.disconnect(client_id)
        try:
            error_msg = WSMessage(type="error", data={"error": str(e)})
            await websocket.send_text(error_msg.to_json())
        except Exception:
            pass
