# QMT OpenAPI Summary (off)

Title: Mist DataSource - QMT
Version: 0.1.0

Generated from the `qmt` FastAPI app in `off` mode.

## GET /health

- Operation ID: `health_health_get`
- Tags: -
- Summary: Health
- Request Body: `-`
- Parameters: -
- Responses: 200: QmtDatasourceHealth

## POST /qmt/bridge/commands

- Operation ID: `enqueue_command_qmt_bridge_commands_post`
- Tags: QMT Bridge
- Summary: Enqueue Command
- Request Body: `CommandRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## GET /qmt/bridge/commands/{command_id}

- Operation ID: `get_command_result_qmt_bridge_commands__command_id__get`
- Tags: QMT Bridge
- Summary: Get Command Result
- Request Body: `-`
- Parameters: command_id (path, string, required=true)
- Responses: 200: object; 422: HTTPValidationError

## GET /qmt/bridge/health

- Operation ID: `bridge_health_qmt_bridge_health_get`
- Tags: QMT Bridge
- Summary: Bridge Health
- Request Body: `-`
- Parameters: -
- Responses: 200: QmtBridgeHealth

## POST /qmt/bridge/owner

- Operation ID: `register_owner_qmt_bridge_owner_post`
- Tags: QMT Bridge
- Summary: Register Owner
- Request Body: `OwnerRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /qmt/bridge/poll

- Operation ID: `poll_commands_qmt_bridge_poll_post`
- Tags: QMT Bridge
- Summary: Poll Commands
- Request Body: `PollRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /qmt/bridge/result

- Operation ID: `post_result_qmt_bridge_result_post`
- Tags: QMT Bridge
- Summary: Post Result
- Request Body: `ResultRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /qmt/bridge/subscriptions/poll

- Operation ID: `poll_subscription_command_qmt_bridge_subscriptions_poll_post`
- Tags: QMT Bridge
- Summary: Poll Subscription Command
- Request Body: `SubscriptionLeaseRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /qmt/bridge/subscriptions/result

- Operation ID: `post_subscription_result_qmt_bridge_subscriptions_result_post`
- Tags: QMT Bridge
- Summary: Post Subscription Result
- Request Body: `SubscriptionResultRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /qmt/bridge/subscriptions/snapshot

- Operation ID: `post_subscription_snapshot_qmt_bridge_subscriptions_snapshot_post`
- Tags: QMT Bridge
- Summary: Post Subscription Snapshot
- Request Body: `SubscriptionSnapshotRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /v1/bars/query

- Operation ID: `query_bars_v1_bars_query_post`
- Tags: V1
- Summary: Query Bars
- Request Body: `QmtBarQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## Schemas

- `CommandRequest`
- `HTTPValidationError`
- `OwnerRequest`
- `PollRequest`
- `QmtBarQueryRequest`
- `QmtBridgeHealth`
- `QmtCommandRejectionTotal`
- `QmtDatasourceHealth`
- `ResultRequest`
- `SubscriptionLeaseRequest`
- `SubscriptionResultFailure`
- `SubscriptionResultRequest`
- `SubscriptionSnapshotRequest`
- `ValidationError`
