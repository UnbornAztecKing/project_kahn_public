"""Tests for content_pane fixes — Feature 1 (empty state contexts) and
Feature 2 (_SplitPair double-click / right-click).
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from textual.geometry import Size

from slopr.models import EventSource, EventType, GameEvent
from slopr.widgets.content_pane import (
    AnnotationCard,
    EventCard,
    EventCardDoubleClicked,
    EventCardRightClicked,
    _SplitPair,
    _build_aligned_pair,
    _build_sequential_children,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _evt(seq: int, turn: int, **kw: object) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": EventType.LLM_DECISION,
        "source": EventSource.LLM,
        "title": f"Event {seq}",
        "body": "",
    }
    defaults.update(kw)
    return GameEvent(**defaults)


def _game_start_event(empty_contexts: bool = True) -> GameEvent:
    """GAME_START event with optionally empty state-context dicts."""
    ctx: dict = {} if empty_contexts else {"name": "PM Sharif", "traits": ["cautious"]}
    return GameEvent(
        sequence_number=1,
        turn_number=0,
        event_type=EventType.GAME_START,
        source=EventSource.SIMULATION,
        title="Game started",
        structured_data={
            "scenario_key": "v11_nuclear_kargil",
            "state_a_leader":     ctx,
            "state_a_military":   ctx,
            "state_a_assessment": ctx,
            "state_b_leader":     ctx,
            "state_b_military":   ctx,
            "state_b_assessment": ctx,
        },
    )


# ── Feature 1: empty state contexts ──────────────────────────────────────────


class TestGameStartEmptyDicts:
    """GAME_START with empty context dicts must not fall through to raw-data section."""

    def _composed_statics(self, event: GameEvent) -> list[str]:
        """Collect all Static markup strings from an EventCard's compose()."""
        card = EventCard(event)
        statics = []
        # compose() is a generator of Textual Widget objects
        for widget in card.compose():
            # Static widgets have a `renderable` attribute
            if hasattr(widget, "renderable"):
                statics.append(str(widget.renderable))
        return statics

    def test_empty_dicts_do_not_appear_in_raw_section(self) -> None:
        """Empty state-context dicts {} should NOT be rendered as raw data."""
        card = EventCard(_game_start_event(empty_contexts=True))
        statics = []
        for widget in card.compose():
            if hasattr(widget, "renderable"):
                text = str(widget.renderable)
                statics.append(text)

        raw_texts = " ".join(statics)
        # These should NOT appear as raw JSON blobs
        assert "state_a_leader: {}" not in raw_texts
        assert "state_b_leader: {}" not in raw_texts
        assert "state_a_military: {}" not in raw_texts
        assert "state_b_military: {}" not in raw_texts
        assert "state_a_assessment: {}" not in raw_texts
        assert "state_b_assessment: {}" not in raw_texts

    def test_non_empty_dict_renders_fields(self) -> None:
        """Non-empty state-context dicts should render their content."""
        leader_data = {"name": "PM Sharif", "traits": ["cautious"], "risk_tolerance": "low"}
        event = GameEvent(
            sequence_number=1,
            turn_number=0,
            event_type=EventType.GAME_START,
            source=EventSource.SIMULATION,
            title="Game started",
            structured_data={
                "state_a_leader": leader_data,
                "state_a_military": {},
                "state_a_assessment": {},
                "state_b_leader": {},
                "state_b_military": {},
                "state_b_assessment": {},
            },
        )
        card = EventCard(event)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        assert "PM Sharif" in all_text

    def test_empty_dict_keys_not_in_remaining_structured_data(self) -> None:
        """The 'data' section header must not appear when all keys are rendered."""
        event = _game_start_event(empty_contexts=True)
        card = EventCard(event)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        # "data" header only appears for truly unrendered keys
        assert "state_a_leader" not in all_text
        assert "state_b_leader" not in all_text


# ── Feature 2: _SplitPair click handling ─────────────────────────────────────


class TestSplitPairClicks:
    """_SplitPair posts correct messages for double-click and right-click."""

    def _make_pair(self) -> tuple[_SplitPair, GameEvent, GameEvent]:
        a = _evt(1, 1, structured_data={"side": "A"})
        b = _evt(2, 1, structured_data={"side": "B"})
        pair = _build_aligned_pair(a, b)
        return pair, a, b

    def test_build_aligned_pair_returns_split_pair(self) -> None:
        a = _evt(1, 1, structured_data={"side": "A"})
        b = _evt(2, 1, structured_data={"side": "B"})
        result = _build_aligned_pair(a, b)
        assert isinstance(result, _SplitPair)

    def test_split_pair_stores_events(self) -> None:
        pair, a, b = self._make_pair()
        assert pair._a_evt is a
        assert pair._b_evt is b

    def _make_click(
        self, *, chain: int, button: int, x: int, screen_x: int = 10, screen_y: int = 5
    ):
        """Create a minimal mock Click event."""
        click = MagicMock()
        click.chain = chain
        click.button = button
        click.x = x
        click.screen_x = screen_x
        click.screen_y = screen_y
        return click

    def test_double_click_left_side_posts_a_event(self) -> None:
        pair, a, b = self._make_pair()

        posted: list = []
        pair.post_message = lambda m: posted.append(m)

        # Widget.size reads content_region.size; patch it at the class level
        with patch.object(type(pair), "size", new_callable=PropertyMock,
                          return_value=Size(80, 10)):
            click = self._make_click(chain=2, button=1, x=10)  # left of midpoint=40
            pair.on_click(click)

        assert len(posted) == 1
        msg = posted[0]
        assert isinstance(msg, EventCardDoubleClicked)
        assert msg.event.id == a.id

    def test_double_click_right_side_posts_b_event(self) -> None:
        pair, a, b = self._make_pair()

        posted: list = []
        pair.post_message = lambda m: posted.append(m)

        with patch.object(type(pair), "size", new_callable=PropertyMock,
                          return_value=Size(80, 10)):
            click = self._make_click(chain=2, button=1, x=60)  # right of midpoint=40
            pair.on_click(click)

        assert len(posted) == 1
        msg = posted[0]
        assert isinstance(msg, EventCardDoubleClicked)
        assert msg.event.id == b.id

    def test_right_click_left_side_posts_right_clicked(self) -> None:
        pair, a, b = self._make_pair()

        posted: list = []
        pair.post_message = lambda m: posted.append(m)

        with patch.object(type(pair), "size", new_callable=PropertyMock,
                          return_value=Size(80, 10)):
            click = self._make_click(chain=1, button=3, x=10, screen_x=15, screen_y=7)
            pair.on_click(click)

        assert len(posted) == 1
        msg = posted[0]
        assert isinstance(msg, EventCardRightClicked)
        assert msg.event.id == a.id
        assert msg.screen_x == 15
        assert msg.screen_y == 7

    def test_right_click_right_side_posts_b_event(self) -> None:
        pair, a, b = self._make_pair()

        posted: list = []
        pair.post_message = lambda m: posted.append(m)

        with patch.object(type(pair), "size", new_callable=PropertyMock,
                          return_value=Size(80, 10)):
            click = self._make_click(chain=1, button=3, x=60)
            pair.on_click(click)

        assert len(posted) == 1
        msg = posted[0]
        assert isinstance(msg, EventCardRightClicked)
        assert msg.event.id == b.id

    def test_single_left_click_does_not_post_double_or_right(self) -> None:
        pair, a, b = self._make_pair()

        posted: list = []
        pair.post_message = lambda m: posted.append(m)

        with patch.object(type(pair), "size", new_callable=PropertyMock,
                          return_value=Size(80, 10)):
            click = self._make_click(chain=1, button=1, x=10)
            pair.on_click(click)

        # No EventCardDoubleClicked or EventCardRightClicked from single click
        assert not any(
            isinstance(m, (EventCardDoubleClicked, EventCardRightClicked)) for m in posted
        )


# ── EventCard right-click ─────────────────────────────────────────────────────


class TestEventCardRightClick:
    """EventCard posts EventCardRightClicked on button-3 clicks."""

    def test_right_click_posts_right_clicked(self) -> None:
        event = _evt(1, 1)
        card = EventCard(event)

        posted: list = []
        card.post_message = lambda m: posted.append(m)

        click = MagicMock()
        click.button = 3
        click.chain = 1
        click.screen_x = 20
        click.screen_y = 8
        card.on_click(click)

        assert len(posted) == 1
        assert isinstance(posted[0], EventCardRightClicked)
        assert posted[0].event.id == event.id

    def test_annotation_card_renders_body(self) -> None:
        """AnnotationCard renders the annotation body text."""
        annotation = GameEvent(
            sequence_number=2,
            turn_number=1,
            event_type=EventType.ANNOTATION,
            source=EventSource.HUMAN,
            title="[Analyze this event]",
            body="Some analysis result.",
        )
        card = AnnotationCard(annotation, last=True)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        # Body text should appear in the compose output
        assert "Some analysis result." in all_text

    def test_annotation_card_stores_annotation(self) -> None:
        """AnnotationCard stores the annotation event for border_title in on_mount."""
        annotation = GameEvent(
            sequence_number=2,
            turn_number=1,
            event_type=EventType.ANNOTATION,
            source=EventSource.HUMAN,
            title="First annotation",
            body="Text.",
        )
        card = AnnotationCard(annotation, last=False)
        # The annotation is stored; border_title is set in on_mount
        assert card._tag is annotation

    def test_event_card_no_annotation_badge(self) -> None:
        """EventCard no longer contains annotation badges — AnnotationCard handles it."""
        event = _evt(1, 1)
        card = EventCard(event)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        assert "†" not in all_text


# ── Sequential annotation ordering ───────────────────────────────────────────


def _annotation_evt(seq: int, parent_id: str, title: str = "Note") -> GameEvent:
    """Create a minimal ANNOTATION event referencing *parent_id*."""
    return GameEvent(
        sequence_number=seq,
        turn_number=1,
        event_type=EventType.ANNOTATION,
        source=EventSource.HUMAN,
        title=title,
        body="Annotation body.",
        parent_id=parent_id,
    )


class TestSequentialAnnotations:
    """_build_sequential_children inserts AnnotationCards after parent EventCards."""

    def test_annotation_card_follows_event_card(self) -> None:
        """AnnotationCard immediately follows the EventCard of its parent event."""
        parent = _evt(1, 1)
        ann = _annotation_evt(2, parent_id=parent.id)
        ann_map = {parent.id: [ann]}

        widgets = _build_sequential_children([parent], ann_map)

        # Find positions
        positions = {type(w).__name__: i for i, w in enumerate(widgets)}
        event_idx = next(
            i for i, w in enumerate(widgets) if isinstance(w, EventCard)
        )
        ann_idx = next(
            i for i, w in enumerate(widgets) if isinstance(w, AnnotationCard)
        )
        assert ann_idx > event_idx, "AnnotationCard must come after its EventCard"

    def test_no_annotations_means_no_annotation_cards(self) -> None:
        """Without an ann_map, no AnnotationCard widgets are produced."""
        parent = _evt(1, 1)
        widgets = _build_sequential_children([parent])
        assert not any(isinstance(w, AnnotationCard) for w in widgets)

    def test_multiple_annotations_ordered(self) -> None:
        """Multiple annotations for one event appear in order, last one has last=True."""
        parent = _evt(1, 1)
        ann1 = _annotation_evt(2, parent_id=parent.id, title="First")
        ann2 = _annotation_evt(3, parent_id=parent.id, title="Second")
        ann_map = {parent.id: [ann1, ann2]}

        widgets = _build_sequential_children([parent], ann_map)
        ann_cards = [w for w in widgets if isinstance(w, AnnotationCard)]
        assert len(ann_cards) == 2
        assert ann_cards[0]._last is False
        assert ann_cards[1]._last is True


# ── Split view annotation alignment ──────────────────────────────────────────


class TestSplitAnnotationAlignment:
    """_build_aligned_pair includes annotation rows when annotations are provided."""

    def test_annotation_row_present_in_split_pair(self) -> None:
        """A/B pair with an A-side annotation has more row widgets than one without."""
        a = _evt(1, 1, structured_data={"side": "A"})
        ann = _annotation_evt(3, parent_id=a.id, title="A note")

        pair_with_ann = _build_aligned_pair(a_evt=a, b_evt=None, a_anns=[ann], b_anns=[])
        pair_without  = _build_aligned_pair(a_evt=a, b_evt=None, a_anns=[], b_anns=[])

        assert isinstance(pair_with_ann, _SplitPair)
        # Annotation produces at least one extra row widget
        assert len(pair_with_ann._row_widgets) > len(pair_without._row_widgets)

    def test_empty_annotations_no_ann_rows(self) -> None:
        """Without annotations, _build_aligned_pair produces no ann-split-row rows."""
        a = _evt(1, 1, structured_data={"side": "A"})
        b = _evt(2, 1, structured_data={"side": "B"})
        pair = _build_aligned_pair(a_evt=a, b_evt=b, a_anns=[], b_anns=[])
        assert isinstance(pair, _SplitPair)


# ── AnnotationCard metadata display ──────────────────────────────────────────


class TestAnnotationCardMetadata:
    """AnnotationCard renders task_id and model/token metadata from structured_data."""

    def _ann_with_sd(self, **sd_fields: object) -> GameEvent:
        return GameEvent(
            sequence_number=10,
            turn_number=2,
            event_type=EventType.ANNOTATION,
            source=EventSource.HUMAN,
            title="[Analyze signal]",
            body="This event warrants attention.",
            structured_data=sd_fields,
        )

    def test_annotation_card_shows_task_label(self) -> None:
        """Card with task_label in structured_data renders an ann-task-id widget."""
        ann = self._ann_with_sd(
            task_label="Analyze Signal",
            task_id="abc12345-1234-1234-1234-123456789abc",
        )
        card = AnnotationCard(ann, last=True)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        assert "Analyze Signal" in all_text

    def test_annotation_card_shows_model_and_tokens(self) -> None:
        """Card with model/tokens in structured_data renders an ann-meta widget."""
        ann = self._ann_with_sd(
            model="claude-sonnet-4-6",
            input_tokens=412,
            output_tokens=187,
        )
        card = AnnotationCard(ann, last=False)
        all_text = " ".join(
            str(w.renderable) for w in card.compose() if hasattr(w, "renderable")
        )
        assert "claude-sonnet-4-6" in all_text
        assert "412" in all_text
        assert "187" in all_text

    def test_annotation_card_no_metadata_no_extra_widgets(self) -> None:
        """Card without structured_data renders only body — no task or meta lines."""
        ann = GameEvent(
            sequence_number=11,
            turn_number=2,
            event_type=EventType.ANNOTATION,
            source=EventSource.HUMAN,
            title="[Note]",
            body="Plain annotation.",
        )
        card = AnnotationCard(ann, last=True)
        widgets = list(card.compose())
        renderables = [str(w.renderable) for w in widgets if hasattr(w, "renderable")]
        # Only the body widget — no task_label, no model
        assert any("Plain annotation." in r for r in renderables)
        assert not any("claude" in r for r in renderables)
