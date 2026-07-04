"""QMT 实时行情 WebSocket 路由.

为 NestJS 后端提供实时行情推送的 WebSocket 接口.
对应 full-QMT bridge 订阅命令。

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

from qmt.routes.dependencies import get_qmt_adapter, get_ws_manager
from src.ws.protocol import WSMessage, ws_error, ws_pong, ws_subscription_ack

router = APIRouter()


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """实时行情 WebSocket 端点.

    NestJS 后端连接此端点以接收实时行情推送. 连接建立后保持长连接，
    通过 JSON 消息进行心跳检测和股票订阅管理.

    对应 full-QMT bridge 订阅命令；生产订阅实现需等待 Windows spike。

    Args:
        websocket: WebSocket 连接实例
        client_id: 客户端标识符，用于区分不同的 NestJS 后端实例

    Examples:
        连接: ws://localhost:9002/ws/quote/nestjs-instance-1
        心跳: {"type": "ping"}
        订阅: {"type": "subscribe", "stocks": ["000001.SZ", "600000.SH"]}
    """
    ws_manager = get_ws_manager(websocket)
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_text(ws_pong(provider="qmt").to_json())
            elif message.get("type") == "subscribe":
                stocks = message.get("stocks", [])
                adapter = get_qmt_adapter(websocket)
                if not adapter:
                    await websocket.send_text(
                        ws_error(
                            provider="qmt",
                            code="QMT_ADAPTER_UNAVAILABLE",
                            message="Adapter not initialized",
                            retryable=True,
                            details={"clientId": client_id},
                        ).to_json()
                    )
                    continue

                await websocket.send_text(
                    ws_subscription_ack(
                        provider="qmt",
                        msg_type="subscribed",
                        accepted=list(stocks),
                        rejected=[],
                        active=list(stocks),
                    ).to_json()
                )

                async for quote_data in adapter.subscribe_quote(stocks):
                    msg = WSMessage(type="quote", data=quote_data)
                    await ws_manager.broadcast(msg)

    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
    except Exception as e:
        await ws_manager.disconnect(client_id)
        try:
            error_msg = ws_error(
                provider="qmt",
                code="QMT_WS_INTERNAL_ERROR",
                message=str(e),
                retryable=True,
                details={"clientId": client_id},
            )
            await websocket.send_text(error_msg.to_json())
        except Exception:
            pass
