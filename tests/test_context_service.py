"""Unit tests for `update_pantry_context`, the spoken shelf-life override."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models import PantryInventory, RipenessModifier
from app.services.context import UNDERRIPE_EXTRA_DAYS, update_pantry_context


class ScalarCollectionResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class ScalarValueResult:
    """Stands in for the `SELECT CURRENT_DATE` the service issues."""

    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


def _item(item_id: int, name: str, expiration: date | None) -> PantryInventory:
    item = PantryInventory(
        id=item_id,
        user_id=7,
        display_name=name,
        custom_expiration_date=None,
    )
    # `expiration_date` is trigger-owned, so in these tests it stands in for
    # whatever Postgres had already computed before the override.
    item.expiration_date = expiration
    return item


def _session(items, today: date | None = None):
    """A session whose refresh mirrors the trigger: custom date wins.

    The service issues two queries on the success path: the item lookup, then
    `SELECT CURRENT_DATE` -- it takes the date from the database rather than
    from Python, so a write cannot disagree with the status view when the two
    clocks straddle midnight. `today` lets a test make them differ on purpose.
    """

    async def refresh(item):
        if item.custom_expiration_date is not None:
            item.expiration_date = item.custom_expiration_date

    return SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarCollectionResult(items),
                ScalarValueResult(today or date.today()),
            ]
        ),
        commit=AsyncMock(),
        refresh=AsyncMock(side_effect=refresh),
    )


def test_very_ripe_closes_the_window_to_tomorrow():
    today = date.today()
    item = _item(1, "Avocados", today + timedelta(days=6))
    session = _session([item])

    result = asyncio.run(
        update_pantry_context(session, 7, "Avocados", RipenessModifier.VERY_RIPE)
    )

    assert result["success"] is True
    assert item.custom_expiration_date == today + timedelta(days=1)
    assert result["item"]["expiration_date"] == (today + timedelta(days=1)).isoformat()
    assert result["item"]["days_remaining"] == 1
    assert result["item"]["previous_expiration_date"] == (
        today + timedelta(days=6)
    ).isoformat()
    session.commit.assert_awaited_once()


def test_smells_off_expires_today_and_recommends_discarding():
    today = date.today()
    item = _item(2, "Plain yogurt", today + timedelta(days=3))
    session = _session([item])

    result = asyncio.run(
        update_pantry_context(session, 7, "Plain yogurt", RipenessModifier.SMELLS_OFF)
    )

    assert item.custom_expiration_date == today
    assert result["item"]["days_remaining"] == 0
    assert result["item"]["discard_recommended"] is True


def test_underripe_extends_from_today_when_the_item_already_expired():
    """An expired item does not become fresh by being called unripe."""
    today = date.today()
    item = _item(3, "Pears", today - timedelta(days=4))
    session = _session([item])

    asyncio.run(
        update_pantry_context(session, 7, "Pears", RipenessModifier.UNDERRIPE)
    )

    assert item.custom_expiration_date == today + timedelta(days=UNDERRIPE_EXTRA_DAYS)


def test_underripe_extends_from_the_computed_date_when_still_fresh():
    today = date.today()
    future = today + timedelta(days=10)
    item = _item(4, "Bananas", future)
    session = _session([item])

    asyncio.run(
        update_pantry_context(session, 7, "Bananas", RipenessModifier.UNDERRIPE)
    )

    assert item.custom_expiration_date == future + timedelta(days=UNDERRIPE_EXTRA_DAYS)


def test_ambiguous_name_returns_candidates_and_writes_nothing():
    today = date.today()
    items = [
        _item(5, "Whole milk", today + timedelta(days=4)),
        _item(6, "Oat milk", today + timedelta(days=9)),
    ]
    session = _session(items)

    result = asyncio.run(
        update_pantry_context(session, 7, "milk", RipenessModifier.VERY_RIPE)
    )

    assert result["success"] is False
    assert set(result["candidates"]) == {"Whole milk", "Oat milk"}
    assert all(item.custom_expiration_date is None for item in items)
    session.commit.assert_not_awaited()


def test_exact_display_name_wins_over_a_partial_match():
    """A client echoing back a name it read from the inventory must not be
    treated as ambiguous just because another item contains that word."""
    today = date.today()
    exact = _item(7, "Milk", today + timedelta(days=4))
    other = _item(8, "Milk chocolate", today + timedelta(days=90))
    session = _session([exact, other])

    result = asyncio.run(
        update_pantry_context(session, 7, "Milk", RipenessModifier.VERY_RIPE)
    )

    assert result["success"] is True
    assert result["item"]["display_name"] == "Milk"
    assert other.custom_expiration_date is None


def test_no_match_reports_the_name_and_writes_nothing():
    session = _session([])

    result = asyncio.run(
        update_pantry_context(session, 7, "Quinoa", RipenessModifier.RIPE)
    )

    assert result["success"] is False
    assert "Quinoa" in result["error"]
    assert result["candidates"] == []
    session.commit.assert_not_awaited()


def test_empty_item_name_is_rejected_before_touching_the_database():
    session = _session([])

    with pytest.raises(ValueError, match="item_name cannot be empty"):
        asyncio.run(
            update_pantry_context(session, 7, "   ", RipenessModifier.RIPE)
        )

    session.execute.assert_not_awaited()


def test_dates_come_from_the_database_clock_not_pythons():
    """Regression: the write must agree with the status view.

    `v_pantry_inventory_status` computes `days_remaining` against the
    database's CURRENT_DATE, which is UTC in the shipped container. When the
    local clock is on the other side of midnight, deriving the target date
    from Python's `date.today()` made the tool report one number while the
    very next read reported another -- observed live as the tool answering
    days_remaining=0 and the inventory then showing -1.
    """
    db_today = date.today() + timedelta(days=1)  # database is a day ahead
    item = _item(9, "Avocados", db_today + timedelta(days=6))
    session = _session([item], today=db_today)

    result = asyncio.run(
        update_pantry_context(session, 7, "Avocados", RipenessModifier.VERY_RIPE)
    )

    # Anchored on the database's day, not the local one.
    assert item.custom_expiration_date == db_today + timedelta(days=1)
    assert result["item"]["days_remaining"] == 1
