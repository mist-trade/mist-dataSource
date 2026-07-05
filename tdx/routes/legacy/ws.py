"""TDX 实时行情 WebSocket 路由.

为 NestJS 后端提供实时行情推送的 WebSocket 接口.
对应 TDX SDK: tqcenter.tq (subscribe_hq, unsubscribe_hq)

使用 TDX 订阅客户端 + 快照采集模式:
    1. TdxLegacySubscriptionClient 包装 subscribe_hq/unsubscribe_hq
    2. SDK 回调只标记 collector dirty symbols
    3. collector 拉取 get_market_snapshot 后广播 quote 事件

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

import json
from contextlib import suppress
from json import JSONDecodeError
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.config import settings
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.ws.protocol import ws_pong, ws_subscription_ack
from tdx.routes.legacy.dependencies import (
    get_tdx_legacy_bridge,
    get_tdx_legacy_subscription_client,
    get_ws_manager,
)

router = APIRouter()


def _get_ws_manager(websocket: WebSocket):
    return get_ws_manager(websocket)


def _get_subscription_client(websocket: WebSocket):
    return get_tdx_legacy_subscription_client(websocket)


def _get_bridge(websocket: WebSocket) -> TdxLegacyBridge:
    return get_tdx_legacy_bridge(websocket)


def _message_symbols(message: dict[str, Any]) -> list[str] | None:
    symbols = message.get("symbols", message.get("stocks", []))
    if not isinstance(symbols, list):
        return None
    symbol_list = cast(list[Any], symbols)
    if not all(isinstance(symbol, str) for symbol in symbol_list):
        return None
    return cast(list[str], symbol_list)


def _is_leader(bridge: TdxLegacyBridge, client_id: str) -> bool:
    return bridge.leader_client_id == client_id or bridge.claim_leader(client_id)


def _subscription_response(
    msg_type: str,
    accepted: list[str],
    rejected: list[str],
    active: list[str],
) -> dict[str, Any]:
    ack_type = "unsubscribed" if msg_type == "unsubscribed" else "subscribed"
    return ws_subscription_ack(
        provider="tdx",
        msg_type=ack_type,
        accepted=accepted,
        rejected=rejected,
        active=active,
    ).model_dump(exclude_none=True)


@router.websocket("/quote/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str):
    """实时行情 WebSocket 端点 (TDX 原生模式).

    使用 TDXSubscriptionClient + TdxLegacyMinuteCollector 模式:
    1. 客户端发送订阅请求
    2. 验证股票数量不超过100只 (TDX SDK限制)
    3. 调用 subscription client 注册轻量回调
    4. 回调只标记 dirty symbol
    5. collector 拉取 snapshot 并广播 quote

    对应 TDX SDK:
        - tq.subscribe_hq(stock_list, callback) - 注册订阅回调
        - tq.unsubscribe_hq(stock_list) - 取消订阅

    Args:
        websocket: WebSocket 连接实例
        client_id: 客户端标识符

    Examples:
        连接: ws://localhost:9001/ws/quote/nestjs-instance-1
        心跳: {"type": "ping"}
        订阅: {"type": "subscribe", "stocks": ["600519.SH", "000001.SZ"]}
    """
    ws_manager = _get_ws_manager(websocket)
    bridge = _get_bridge(websocket)
    if not await ws_manager.connect_unique(websocket, client_id):
        await websocket.accept()
        await websocket.send_text(
            json.dumps(
                bridge.make_error_message(
                    "DATASOURCE_WS_DUPLICATE_CLIENT",
                    "A WebSocket client with this client_id is already connected",
                    False,
                    {"clientId": client_id},
                )
            )
        )
        await websocket.close()
        return

    bridge.claim_leader(client_id)
    await websocket.send_text(json.dumps(bridge.make_ready_message()))

    subscription_client = _get_subscription_client(websocket)
    if not subscription_client:
        await websocket.send_text(
            json.dumps(
                bridge.make_error_message(
                    "TDX_SUBSCRIPTION_CLIENT_UNAVAILABLE",
                    "Subscription client not initialized",
                    True,
                    {},
                )
            )
        )
        await websocket.close()
        bridge.disconnect(client_id)
        await ws_manager.disconnect(client_id)
        return

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except JSONDecodeError as e:
                await websocket.send_text(
                    json.dumps(
                        bridge.make_error_message(
                            "DATASOURCE_WS_INVALID_MESSAGE",
                            "WebSocket message must be valid JSON",
                            False,
                            {"error": str(e)},
                        )
                    )
                )
                continue

            msg_type = message.get("type")

            if msg_type == "ping":
                # 心跳响应
                await websocket.send_text(ws_pong(provider="tdx").to_json())

            elif msg_type in {"sync_subscriptions", "subscribe", "unsubscribe"}:
                if not _is_leader(bridge, client_id):
                    await websocket.send_text(
                        json.dumps(
                            bridge.make_error_message(
                                "DATASOURCE_WS_NOT_LEADER",
                                "Only the command leader can change TDX subscriptions",
                                False,
                                {"leaderClientId": bridge.leader_client_id},
                            )
                        )
                    )
                    continue

                symbols = _message_symbols(message)
                if symbols is None:
                    await websocket.send_text(
                        json.dumps(
                            bridge.make_error_message(
                                "DATASOURCE_WS_INVALID_SYMBOLS",
                                "WebSocket symbols must be a list of strings",
                                False,
                                {"operation": msg_type},
                            )
                        )
                    )
                    continue

                try:
                    if msg_type == "sync_subscriptions":
                        result = await subscription_client.sync(symbols)
                    elif msg_type == "subscribe":
                        result = await subscription_client.subscribe(symbols)
                    else:
                        result = await subscription_client.unsubscribe(symbols)

                    error = result.get("error")
                    if error:
                        await websocket.send_text(
                            json.dumps(
                                bridge.make_error_message(
                                    error["code"],
                                    error["message"],
                                    bool(error.get("retryable", False)),
                                    error.get(
                                        "details",
                                        {"maxSubscriptions": settings.tdx.max_subscriptions},
                                    ),
                                )
                            )
                        )
                        continue

                    response_type = "unsubscribed" if msg_type == "unsubscribe" else "subscribed"
                    await websocket.send_text(
                        json.dumps(
                            _subscription_response(
                                response_type,
                                list(result.get("accepted", symbols)),
                                list(result.get("rejected", [])),
                                list(result.get("active", bridge.active_subscriptions)),
                            )
                        )
                    )
                except Exception as e:
                    await websocket.send_text(
                        json.dumps(
                            bridge.make_error_message(
                                "TDX_SUBSCRIPTION_FAILED",
                                f"Subscription change failed: {str(e)}",
                                True,
                                {"operation": msg_type},
                            )
                        )
                    )

            elif msg_type == "error":
                # 客户端错误
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        with suppress(Exception):
            await websocket.send_text(
                json.dumps(
                    bridge.make_error_message(
                        "TDX_WS_INTERNAL_ERROR",
                        str(e),
                        True,
                        {},
                    )
                )
            )

    finally:
        if bridge.leader_client_id == client_id and bridge.active_subscriptions:
            with suppress(Exception):
                await subscription_client.unsubscribe(list(bridge.active_subscriptions))

        bridge.disconnect(client_id)
        await ws_manager.disconnect(client_id)
