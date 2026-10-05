"""Checks on parsed events: identity (suspected duplicates) and invariants."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .models import Reason, Side, TradeEvent, Violation

TradeKey = tuple[str, str, Side, Decimal, datetime]


def trade_key(event: TradeEvent) -> TradeKey | None:
    """The values that describe the trade itself, leaving out the delivery id.

    None when block_time is missing: such a row can't be matched until it's
    backfilled.
    """
    if event.block_time is None:
        return None
    return (event.tx_hash, event.wallet, event.side, event.amount, event.block_time)


class DuplicateIndex:
    """Flags events that repeat a trade already seen.

    The feed has no trade identifier, so a match is only a suspicion: one
    transaction can hold two identical trades. The first event seen for a key
    is the reference; every later match is flagged, including an exact repeat
    of the same event_id.
    """

    def __init__(self) -> None:
        self._first: dict[TradeKey, str] = {}

    def check(self, event: TradeEvent) -> list[Violation]:
        key = trade_key(event)
        if key is None:
            return []
        if key not in self._first:
            self._first[key] = event.event_id
            return []
        detail = f"same trade as {self._first[key]}"
        return [Violation(Reason.SUSPECTED_DUPLICATE, None, detail)]


def check_invariants(event: TradeEvent) -> list[Violation]:
    """An event can't be ingested before its block exists."""
    if event.block_time is None or event.ingested_at >= event.block_time:
        return []
    detail = f"ingested {event.block_time - event.ingested_at} before block_time"
    return [Violation(Reason.INGESTED_BEFORE_BLOCK, None, detail)]
