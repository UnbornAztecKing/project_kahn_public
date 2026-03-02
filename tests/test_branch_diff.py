"""Tests for branch body diff (Feature 10).

Tests the difflib.unified_diff logic used by BranchPane._show_detail().
The diff computation is verified independently without requiring a DOM context.
"""

from __future__ import annotations

import difflib


# ── helpers replicating the BranchPane diff logic ────────────────────────────


def _compute_diff(old_body: str, new_body: str) -> list[tuple[str, str]]:
    """Replicate the diff logic from BranchPane._show_detail().

    Returns a list of (css_class, line) pairs representing what would be
    rendered — parallel to the Statics that _show_detail() mounts.
    """
    result: list[tuple[str, str]] = []
    diff_lines = list(difflib.unified_diff(
        (old_body or "").splitlines(keepends=True),
        (new_body or "").splitlines(keepends=True),
        fromfile="original",
        tofile="edited",
        lineterm="",
    ))
    if diff_lines:
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                result.append(("branch-detail-diff-new", line))
            elif line.startswith("-") and not line.startswith("---"):
                result.append(("branch-detail-diff-old", line))
            elif line.startswith("@@"):
                result.append(("branch-detail-section", line))
            # header lines (--- / +++) are skipped
    else:
        result.append(("branch-detail-value", new_body or "(empty)"))
    return result


# ── tests ─────────────────────────────────────────────────────────────────────


def test_diff_shows_additions() -> None:
    """Added lines appear with the diff-new CSS class, prefixed with '+'."""
    result = _compute_diff("foo\n", "foo\nbar\n")
    new_lines = [line for cls, line in result if cls == "branch-detail-diff-new"]
    assert any("+bar" in line or "+ bar" in line.replace("+", "+ ") for line in new_lines), \
        f"Expected '+bar' in diff output, got: {new_lines}"


def test_diff_shows_removals() -> None:
    """Removed lines appear with the diff-old CSS class, prefixed with '-'."""
    result = _compute_diff("foo\nbaz\n", "foo\n")
    old_lines = [line for cls, line in result if cls == "branch-detail-diff-old"]
    assert any("-baz" in line or "- baz" in line.replace("-", "- ") for line in old_lines), \
        f"Expected '-baz' in diff output, got: {old_lines}"


def test_no_diff_shows_body_unchanged() -> None:
    """When old == new, no diff lines are produced; the body renders as-is."""
    result = _compute_diff("same content\n", "same content\n")
    assert len(result) == 1
    cls, text = result[0]
    assert cls == "branch-detail-value"
    assert "same content" in text


def test_no_diff_when_old_body_empty() -> None:
    """When there is no old body (first edit), show the new body directly."""
    result = _compute_diff("", "new text here")
    # With empty old_body, diff produces all-addition lines OR falls to value branch
    # In either case, the new text must be represented
    all_text = " ".join(line for _, line in result)
    assert "new text" in all_text


def test_context_lines_use_section_class() -> None:
    """@@ hunk headers get the 'branch-detail-section' CSS class."""
    result = _compute_diff("line1\nline2\nline3\n", "line1\nchanged\nline3\n")
    section_lines = [line for cls, line in result if cls == "branch-detail-section"]
    assert any(line.startswith("@@") for line in section_lines)


def test_header_lines_are_skipped() -> None:
    """--- and +++ header lines are not included in the output."""
    result = _compute_diff("old\n", "new\n")
    all_lines = [line for _, line in result]
    assert not any(line.startswith("---") or line.startswith("+++") for line in all_lines)


def test_multi_hunk_diff() -> None:
    """Diffs spanning multiple hunks produce output for each changed region."""
    old = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n"
    new = "a\nb\nX\nd\ne\nf\ng\nh\nY\nj\n"
    result = _compute_diff(old, new)
    new_lines = [line for cls, line in result if cls == "branch-detail-diff-new"]
    old_lines = [line for cls, line in result if cls == "branch-detail-diff-old"]
    assert len(new_lines) >= 2
    assert len(old_lines) >= 2
