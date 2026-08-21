# Droid Sessions API

Create and drive Droid sessions: manage their lifecycle, settings, and messages.

## List sessions

`GET /api/v0/sessions`

Returns a paginated list of sessions for the authenticated user. This feature is enabled for selected organizations only.

```bash
curl 'https://api.factory.ai/api/v0/sessions' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `limit` (`string`) - Query parameter. Maximum number of items to return (1-100)
- `cursor` (`string`) - Query parameter. Cursor for pagination
- `computerId` (`string`) - Query parameter. Computer ID to query directly

**Response:** `200` - Response for status 200

## Create a session

`POST /api/v0/sessions`

Creates a new session with the specified configuration. This feature is enabled for selected organizations only.

```bash
curl -X POST 'https://api.factory.ai/api/v0/sessions' \
  -H 'Authorization: Bearer $FACTORY_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{ ... }'
```

**Response:** `201` - Response for status 201

## Get a session

`GET /api/v0/sessions/{sessionId}`

Returns detailed session information including settings and stats. This feature is enabled for selected organizations only.

```bash
curl 'https://api.factory.ai/api/v0/sessions/{sessionId}' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter. Session ID
- `computerId` (`string`) - Query parameter. Computer ID to query directly

**Response:** `200` - Response for status 200

## Delete a session

`DELETE /api/v0/sessions/{sessionId}`

Soft-deletes a session (can be restored within retention period). This feature is enabled for selected organizations only.

```bash
curl -X DELETE 'https://api.factory.ai/api/v0/sessions/{sessionId}' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter. Session ID
- `computerId` (`string`) - Query parameter. Computer ID to query directly

**Response:** `204` - Response for status 204

## Update a session

`PATCH /api/v0/sessions/{sessionId}`

Updates session configuration such as model and reasoning effort. This feature is enabled for selected organizations only.

```bash
curl -X PATCH 'https://api.factory.ai/api/v0/sessions/{sessionId}' \
  -H 'Authorization: Bearer $FACTORY_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{ ... }'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter. Session ID

**Response:** `200` - Response for status 200

## Interrupt a session

`POST /api/v0/sessions/{sessionId}/interrupt`

Interrupts a running agent loop. Idempotent if already idle. This feature is enabled for selected organizations only.

```bash
curl -X POST 'https://api.factory.ai/api/v0/sessions/{sessionId}/interrupt' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter

**Response:** `200` - Response for status 200

## Get session messages

`GET /api/v0/sessions/{sessionId}/messages`

Returns paginated message history with optional role filtering. This feature is enabled for selected organizations only.

```bash
curl 'https://api.factory.ai/api/v0/sessions/{sessionId}/messages' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter
- `limit` (`string`) - Query parameter. Maximum number of items to return (1-100)
- `cursor` (`string`) - Query parameter. Cursor for pagination
- `computerId` (`string`) - Query parameter. Computer ID to query directly
- `role` (`string`) - Query parameter. Filter messages by role Allowed values: user, assistant, tool.

**Response:** `200` - Response for status 200

## Add a message to a session

`POST /api/v0/sessions/{sessionId}/messages`

Adds a user message and optionally waits for agent completion. Supports text, images, and file attachments. This feature is enabled for selected organizations only.

```bash
curl -X POST 'https://api.factory.ai/api/v0/sessions/{sessionId}/messages' \
  -H 'Authorization: Bearer $FACTORY_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{ ... }'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter

**Response:** `200` - Response for status 200

## Get a message by ID

`GET /api/v0/sessions/{sessionId}/messages/{messageId}`

Returns a single message from the session by its ID. This feature is enabled for selected organizations only.

```bash
curl 'https://api.factory.ai/api/v0/sessions/{sessionId}/messages/{messageId}' \
  -H 'Authorization: Bearer $FACTORY_API_KEY'
```

**Parameters**

- `sessionId` (`string`, required) - Path parameter. Session ID
- `messageId` (`string`, required) - Path parameter. Message ID
- `computerId` (`string`) - Query parameter. Computer ID to query directly

**Response:** `200` - Response for status 200
