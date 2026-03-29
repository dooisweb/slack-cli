"""Socket Mode listener — real-time event handling via WebSocket."""

import logging
from collections.abc import Awaitable, Callable

from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient

from slack_tui.models import Message


class SocketListener:
    """Wraps the Slack Socket Mode client for real-time message events."""

    def __init__(
        self,
        app_token: str,
        bot_token: str,
        on_message: Callable[[Message], Awaitable[None]],
    ) -> None:
        self.client = SocketModeClient(
            app_token=app_token,
            web_client=AsyncWebClient(token=bot_token),
        )
        self.on_message = on_message
        self.client.socket_mode_request_listeners.append(self._handle_request)

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        await self.client.connect()

    async def disconnect(self) -> None:
        """Clean shutdown."""
        await self.client.disconnect()

    async def _handle_request(
        self, client: SocketModeClient, req: SocketModeRequest
    ) -> None:
        """Process incoming Socket Mode envelopes."""
        # Always acknowledge first
        response = SocketModeResponse(envelope_id=req.envelope_id)
        await client.send_socket_mode_response(response)

        log = logging.getLogger(__name__)
        log.debug("Socket event received: type=%s, payload_keys=%s", req.type, list(req.payload.keys()) if req.payload else [])

        if req.type == "events_api":
            event = req.payload.get("event", {})
            log.debug("Event: type=%s, subtype=%s, channel=%s, user=%s",
                      event.get("type"), event.get("subtype"), event.get("channel"),
                      event.get("user"))
            if event.get("type") == "message" and "subtype" not in event:
                ts = event.get("ts")
                channel_id = event.get("channel")
                if not ts or not channel_id:
                    log.warning("Malformed message event: missing ts or channel")
                    return
                try:
                    timestamp = float(ts.split(".")[0])
                except (ValueError, IndexError):
                    timestamp = 0.0
                message = Message(
                    ts=ts,
                    channel_id=channel_id,
                    user_id=event.get("user", "unknown"),
                    user_name="",  # Resolved by the app layer
                    text=event.get("text", ""),
                    timestamp=timestamp,
                )
                await self.on_message(message)
