"""WebSocket routes for TDX adapter."""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from instance1.main import ws_manager
from src.ws.protocol import WSMessage

router = APIRouter()


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """NestJS 连接此端点接收实时行情推送.

    Args:
        websocket: WebSocket connection
        client_id: Client identifier (e.g., NestJS instance name)
    """
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            # 保持连接，接收心跳和订阅请求
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "subscribe":
                # 处理订阅请求（TODO: 实现动态订阅）
                stocks = message.get("stocks", [])
                # TODO: 启动实时行情推送任务
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
        await ws_manager.disconnect(client_id)
    except Exception as e:
        await ws_manager.disconnect(client_id)
        # Send error message if possible
        try:
            error_msg = WSMessage(type="error", data={"error": str(e)})
            await websocket.send_text(error_msg.to_json())
        except Exception:
            pass
