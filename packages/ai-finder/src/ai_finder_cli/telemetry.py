"""Telemetry module for AI Finder CLI.

Collects anonymous usage data to help improve the tool.
No file paths, scan targets, or PII are ever collected.

Opt-out methods:
- Set AI_FINDER_TELEMETRY=0 environment variable
- Set DO_NOT_TRACK=1 environment variable
- Create ~/.ai-finder/config.json with {"telemetry": false}
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Generator

from ai_finder_cli import __version__

# Ingest key for ai-finder project
_INGEST_KEY = "ik_eOC-YBXtnuNN-jbNSjgcr0p2ppDUPHSRxABcIrCC-d0"
_PROJECT_SLUG = "ai-finder"

# Global telemetry client (lazily initialized)
_client: Any = None
_disabled_by_flag: bool = False


def _get_config_path() -> Path:
    """Get the ai-finder config directory path."""
    return Path.home() / ".ai-finder"


def _check_config_opt_out() -> bool:
    """Check if telemetry is disabled via config file at ~/.ai-finder/config.json."""
    config_path = _get_config_path() / "config.json"
    if not config_path.exists():
        return False
    try:
        config = json.loads(config_path.read_text())
        return config.get("telemetry") is False
    except Exception:
        # Fail closed: if config is unreadable, assume opt-out (privacy-first)
        return True


def _is_disabled() -> bool:
    """Check if telemetry is disabled via any mechanism."""
    if _disabled_by_flag:
        return True
    if os.environ.get("AI_FINDER_TELEMETRY") == "0":
        return True
    if os.environ.get("DO_NOT_TRACK") == "1":
        return True
    return bool(_check_config_opt_out())


def _get_client() -> Any:
    """Get or create the telemetry client."""
    global _client

    if _client is not None:
        return _client

    if _is_disabled():
        return None

    try:
        from ptelemetry import Telemetry

        _client = Telemetry(
            write_key=_INGEST_KEY,
            project_slug=_PROJECT_SLUG,
        )
        return _client
    except ImportError:
        # ptelemetry not installed - silently disable
        return None
    except Exception:
        # Any initialization error - silently disable
        return None


def disable() -> None:
    """Disable telemetry for this session (called when --no-telemetry flag is used).

    Also shuts down any already-initialized client to ensure no further events are sent.
    """
    global _disabled_by_flag, _client
    _disabled_by_flag = True
    # Shutdown and reset any existing client
    if _client is not None:
        with suppress(Exception):
            _client.shutdown()
        _client = None


def track_cli_started() -> None:
    """Track CLI startup event."""
    client = _get_client()
    if client:
        client.track(
            "cli.started",
            properties={"version": __version__},
        )
        # Flush immediately to ensure this event is sent
        with suppress(Exception):
            client.flush()


def track_command_started(command: str, properties: dict[str, Any] | None = None) -> None:
    """Track command start event."""
    client = _get_client()
    if client:
        props = {"command": command}
        if properties:
            props.update(properties)
        client.track(f"command.{command}.started", properties=props)
        # Flush immediately to ensure this event is sent before long-running commands
        with suppress(Exception):
            client.flush()


def track_command_completed(
    command: str,
    success: bool,
    duration_ms: int,
    properties: dict[str, Any] | None = None,
) -> None:
    """Track command completion event."""
    client = _get_client()
    if client:
        props = {
            "command": command,
            "success": success,
            "duration_ms": duration_ms,
        }
        if properties:
            props.update(properties)
        client.track(f"command.{command}.completed", properties=props)
        # Flush immediately to ensure completion event is sent
        with suppress(Exception):
            client.flush()


def track_error(exception: Exception, context: str | None = None) -> None:
    """Track an error event with granular discrete events.

    PRIVACY: Only sends exception type and category.
    File paths and stack traces are NOT sent.

    Emits discrete error events for funnel analysis:
        error.scan.file_not_found
        error.identify.permission_denied
        error.kb.database_error
    """
    client = _get_client()
    if client:
        error_type = type(exception).__name__

        # Classify error into categories for funnel analysis
        error_category = _classify_error(exception)

        # Emit discrete error event for funnel
        if context:
            client.track(f"error.{context}.{error_category}")
        else:
            client.track(f"error.{error_category}")

        # Also emit generic error with properties for detailed analysis
        props = {"error_type": error_type, "error_category": error_category}
        if context:
            props["context"] = context
        client.track("error", properties=props, event_type="error")


def _classify_error(exception: Exception) -> str:
    """Classify an exception into a category for telemetry.

    Returns a snake_case category string that's safe for event names.
    """
    error_type = type(exception).__name__

    # File/IO errors
    if isinstance(exception, FileNotFoundError):
        return "file_not_found"
    if isinstance(exception, PermissionError):
        return "permission_denied"
    if isinstance(exception, IsADirectoryError):
        return "is_directory"
    if isinstance(exception, NotADirectoryError):
        return "not_a_directory"
    if isinstance(exception, OSError):
        # Check for specific OS errors
        if hasattr(exception, "errno"):
            import errno

            if exception.errno == errno.ENOSPC:
                return "disk_full"
            if exception.errno == errno.ENOMEM:
                return "out_of_memory"
            if exception.errno == errno.ELOOP:
                return "symlink_loop"
        return "os_error"

    # Memory errors
    if isinstance(exception, MemoryError):
        return "out_of_memory"

    # Value/Type errors
    if isinstance(exception, ValueError):
        return "invalid_value"
    if isinstance(exception, TypeError):
        return "type_error"
    if isinstance(exception, KeyError):
        return "key_error"

    # Network errors
    if "ConnectionError" in error_type or "Timeout" in error_type:
        return "network_error"
    if "HTTPError" in error_type:
        return "http_error"

    # Database errors
    if "sqlite" in error_type.lower() or "database" in error_type.lower():
        return "database_error"

    # Parse/Format errors
    if "Parse" in error_type or "Decode" in error_type or "JSON" in error_type:
        return "parse_error"
    if "UnicodeError" in error_type or isinstance(exception, UnicodeError):
        return "encoding_error"

    # Generic fallback
    return "unknown"


def track_event(event: str, properties: dict[str, Any] | None = None) -> None:
    """Track a generic event.

    This can be used as a callback for libraries that need to emit telemetry.

    Args:
        event: Event name (e.g., "enrichment.kb_hit")
        properties: Event properties (must not contain file paths or PII)
    """
    client = _get_client()
    if client:
        client.track(event, properties=properties or {})


def track_feature(command: str, feature: str, value: str | None = None) -> None:
    """Track a discrete feature usage event for funnel analysis.

    Emits events like:
        scan.format.cyclonedx
        scan.enrich.enabled
        identify.kb_match.found

    These discrete events enable funnel visualization without needing
    to parse property payloads.

    Args:
        command: Command name (e.g., "scan", "identify")
        feature: Feature name (e.g., "format", "enrich", "kb_match")
        value: Feature value (e.g., "cyclonedx", "enabled", "found")
    """
    client = _get_client()
    if client:
        event_name = f"{command}.{feature}.{value}" if value else f"{command}.{feature}"
        client.track(event_name)


@contextmanager
def track_command(
    command: str,
    start_properties: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager to track command execution.

    Usage:
        with track_command("scan", {"format": "json"}) as ctx:
            # do work
            ctx["findings_count"] = 42  # add completion properties

    Args:
        command: Command name (e.g., "scan", "identify")
        start_properties: Properties to include in the started event

    Yields:
        Dict to collect additional properties for the completed event
    """
    completion_props: dict[str, Any] = {}
    start_time = time.perf_counter()

    track_command_started(command, start_properties)

    success = False
    try:
        yield completion_props
        success = True
    except Exception as e:
        track_error(e, context=command)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        track_command_completed(command, success, duration_ms, completion_props)


def shutdown() -> None:
    """Shutdown the telemetry client, flushing any pending events."""
    global _client
    if _client is not None:
        with suppress(Exception):
            _client.shutdown()
        _client = None
