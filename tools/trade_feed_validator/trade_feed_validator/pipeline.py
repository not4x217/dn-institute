"""Run every check on each row and route it to clean or quarantine."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .checks import DuplicateIndex, check_invariants
from .models import QuarantinedRow, RawRow, TradeEvent
from .parsing import parse_row, read_rows


@dataclass
class ValidationResult:
    clean: list[TradeEvent] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)


class Validator:
    """Validates rows in arrival order.

    State lives across a run: the duplicate index remembers every trade seen,
    so rows resolved later (e.g. backfilled) are checked against the same
    reference set.

    Duplicates are matched on block_time, so only rows whose block_time can
    be trusted are matched: a missing or impossible time is matched once the
    chain has supplied the real one.
    """

    def __init__(self) -> None:
        self.duplicates = DuplicateIndex()

    def validate_row(self, line: int, raw: RawRow) -> TradeEvent | QuarantinedRow:
        parsed = parse_row(line, raw)
        violations = list(parsed.violations)
        if parsed.event is not None:
            # An impossible block_time would match the wrong trade, so such a
            # row is matched for duplicates only after resolution.
            violations += check_invariants(parsed.event) or self.duplicates.check(parsed.event)
        if violations:
            return QuarantinedRow(line, raw, tuple(violations), parsed.event)
        return parsed.event

    def validate(self, rows: Iterable[tuple[int, RawRow]]) -> ValidationResult:
        result = ValidationResult()
        for line, raw in rows:
            outcome = self.validate_row(line, raw)
            if isinstance(outcome, QuarantinedRow):
                result.quarantined.append(outcome)
            else:
                result.clean.append(outcome)
        return result

    def validate_file(self, path: str | Path) -> ValidationResult:
        return self.validate(read_rows(path))
