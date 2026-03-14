from __future__ import annotations

import logging
import socket

from aptdata.core.events import EventPayload

logger = logging.getLogger(__name__)


class UDPTelemetryListener:
    """A highly optimized telemetry listener for the EventBus.

    This listener serialize events into JSON Lines and offloads them
    asynchronously to a local observability agent (like OpenTelemetry Collector
    or an Apache Kafka proxy) via UDP. This entirely avoids blocking TCP/HTTP
    calls or synchronous database inserts, fitting the requirement for zero
    overhead in high throughput corporate environments.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5555) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __call__(self, event: EventPayload) -> None:
        """Invoked by the EventBus daemon thread.

        Serializes the event via Pydantic's `model_dump_json` to guarantee
        a valid JSON Lines contract and sends it over UDP in a fire-and-forget
        manner.
        """
        try:
            # model_dump_json creates a serialized JSON string.
            payload_json = event.model_dump_json() + "\n"
            self._sock.sendto(payload_json.encode("utf-8"), (self.host, self.port))
        except Exception as e:
            # Failures in the observability listener should not block the main
            # flow. They are just logged. The EventBus wrapper also catches exceptions,
            # but we catch them here to add more specific context if needed.
            logger.debug(f"Failed to offload telemetry event via UDP: {e}")
