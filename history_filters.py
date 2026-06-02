"""Date parsing and SQL filter helpers for history queries."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple


class DateRange(NamedTuple):
    start: date
    end: date


_DATE_SEPARATORS = re.compile(r"[-/.]")


def parse_date_token(text: str) -> date | None:
    value = text.strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    parts = _DATE_SEPARATORS.split(value)
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, day = (int(part) for part in parts)
        try:
            return date(year, month, day)
        except ValueError:
            return None

    spaced = re.match(r"^(\d{4})\s+(\d{1,2})\s+(\d{1,2})$", value)
    if spaced:
        year, month, day = (int(part) for part in spaced.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def parse_range_token(text: str) -> DateRange | None:
    value = text.strip()
    if not value:
        return None

    if ".." in value:
        start_text, end_text = value.split("..", 1)
        start = parse_date_token(start_text)
        end = parse_date_token(end_text)
        if start is None or end is None:
            return None
        if start > end:
            start, end = end, start
        return DateRange(start, end)

    single = parse_date_token(value)
    if single is None:
        return None
    return DateRange(single, single)


def parse_ranges(tokens: list[str]) -> list[DateRange]:
    ranges: list[DateRange] = []
    seen: set[tuple[date, date]] = set()
    for token in tokens:
        parsed = parse_range_token(token)
        if parsed is None:
            continue
        key = (parsed.start, parsed.end)
        if key in seen:
            continue
        seen.add(key)
        ranges.append(parsed)
    return ranges


def q_to_date_range(query: str) -> DateRange | None:
    return parse_range_token(query.strip())


def build_date_or_clause(
    column: str,
    ranges: list[DateRange],
) -> tuple[str, list[str]]:
    if not ranges:
        return "", []

    parts: list[str] = []
    params: list[str] = []
    for item in ranges:
        parts.append(f"(date({column}) >= date(?) AND date({column}) <= date(?))")
        params.extend([item.start.isoformat(), item.end.isoformat()])
    return f"({' OR '.join(parts)})", params
