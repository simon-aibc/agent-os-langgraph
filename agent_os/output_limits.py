"""Shared byte limits for values retained in graph state."""

BASH_OUTPUT_MAX_BYTES = 100 * 1024
DISPATCHER_OUTPUT_MAX_BYTES = 50 * 1024


def truncate_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
    """Return a UTF-8-safe, byte-limited value and its truncation status.

    Truncated values start with ``[truncated N bytes]\n``, where ``N`` is the
    exact number of original payload bytes omitted. If ``max_bytes`` is too
    small to hold even that marker, an empty string is returned.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False

    # The marker for the complete payload is at least as long as the final
    # marker because the final omitted-byte count cannot have more digits.
    conservative_marker = f"[truncated {len(encoded)} bytes]\n".encode()
    payload_budget = max_bytes - len(conservative_marker)
    if payload_budget < 0:
        return "", True

    retained = encoded[:payload_budget].decode("utf-8", errors="ignore")
    retained_bytes = retained.encode("utf-8")
    omitted_bytes = len(encoded) - len(retained_bytes)
    marker = f"[truncated {omitted_bytes} bytes]\n"

    result = marker + retained
    assert len(result.encode("utf-8")) <= max_bytes
    return result, True
