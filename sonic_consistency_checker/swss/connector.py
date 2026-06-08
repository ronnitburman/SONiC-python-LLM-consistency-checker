"""Optional SWSS SDK import handling.

SWSS SDK (swsssdk, swsscommon) may only be available inside the SONiC container.
This module handles imports gracefully — never crashes on ImportError.
"""

from __future__ import annotations

from typing import Any


class SwssSdkUnavailable(Exception):
    """Raised when SWSS SDK modules are not importable."""


def require_swsssdk() -> Any:
    """Return the swsssdk module, or raise SwssSdkUnavailable."""
    try:
        import swsssdk  # type: ignore[import-untyped]
        return swsssdk
    except ImportError as exc:
        raise SwssSdkUnavailable(
            "swsssdk is not available in this Python environment. "
            "Run this command inside the SONiC container or use raw Redis mode."
        ) from exc


def require_swsscommon() -> Any:
    """Return swsscommon.swsscommon, or raise SwssSdkUnavailable."""
    try:
        from swsscommon import swsscommon  # type: ignore[import-untyped]
        return swsscommon
    except ImportError as exc:
        raise SwssSdkUnavailable(
            "swsscommon is not available in this Python environment. "
            "Run this command inside the SONiC container or use raw Redis mode."
        ) from exc


def swss_available() -> dict[str, Any]:
    """Check availability of SWSS SDK modules.

    Returns a dict with keys: swsssdk_available, swsscommon_available,
    available, message, errors.
    """
    status: dict[str, Any] = {
        "swsssdk_available": False,
        "swsscommon_available": False,
        "available": False,
        "message": "",
        "errors": [],
    }

    try:
        require_swsssdk()
        status["swsssdk_available"] = True
    except Exception as exc:
        status["errors"].append(str(exc))

    try:
        require_swsscommon()
        status["swsscommon_available"] = True
    except Exception as exc:
        status["errors"].append(str(exc))

    status["available"] = bool(
        status["swsssdk_available"] or status["swsscommon_available"]
    )

    if status["available"]:
        status["message"] = (
            "SWSS SDK support is available in this environment."
        )
    else:
        status["message"] = (
            "SWSS SDK is not available in this Python environment. "
            "Try running inside the SONiC container, or continue using "
            "raw Redis mode."
        )

    return status
