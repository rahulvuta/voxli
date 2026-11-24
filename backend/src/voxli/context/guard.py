"""Verbatim guard: model output may only be metadata that references real utterance IDs.

Never touches utterance text. check_event() returns a violation string or None.
"""
from __future__ import annotations

import re

from ..types import Utterance

THREAD_RE = re.compile(r"^t\d{1,3}$")
KINDS = {"self_intro", "introduced", "correction"}
KEYS = {
    "annotation": {"type", "utterance_id", "reply_to", "interrupts", "thread_id", "incomplete"},
    "name_suggestion": {"type", "id", "speaker_id", "name", "evidence_utterance_id", "kind", "auto_applied"},
}
ITEM_KEYS = {"speaker_id", "utterance_ids", "summary"}


def find_name(name: str, text: str) -> str | None:
    """The name as spelled in `text` (whole word, case-insensitive), else None."""
    m = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I)
    return m.group(0) if m else None


def _valid_name(n) -> bool:
    return isinstance(n, str) and 0 < len(n) <= 32 and len(n.split()) <= 3 and n[0].isalpha() and not any(c.isdigit() for c in n)


def check_event(ev: dict, by_id: dict[str, Utterance]) -> str | None:
    t = ev.get("type")
    if t in KEYS:
        if set(ev) != KEYS[t]:
            return f"{t}: unexpected keys {sorted(set(ev) ^ KEYS[t])}"
    if t == "annotation":
        if ev["utterance_id"] not in by_id:
            return "annotation: unknown utterance_id"
        for k in ("reply_to", "interrupts"):
            if ev[k] is not None and ev[k] not in by_id:
                return f"annotation: unknown {k}"
        if ev["thread_id"] is not None and not THREAD_RE.match(str(ev["thread_id"])):
            return "annotation: bad thread_id"
        if not isinstance(ev["incomplete"], bool):
            return "annotation: incomplete not bool"
    elif t == "name_suggestion":
        u = by_id.get(ev["evidence_utterance_id"])
        if u is None:
            return "name_suggestion: unknown evidence id"
        if not _valid_name(ev["name"]) or not find_name(ev["name"], u.text):
            return "name_suggestion: name not in evidence text"
        if ev["kind"] not in KINDS or not isinstance(ev["auto_applied"], bool):
            return "name_suggestion: bad kind/auto_applied"
    elif t == "catch_up":
        for it in ev["items"]:
            if set(it) != ITEM_KEYS or not isinstance(it["summary"], str) or len(it["summary"].split()) > 15:
                return "catch_up: bad item"
            for i in it["utterance_ids"]:
                if i not in by_id or by_id[i].speaker_id != it["speaker_id"]:
                    return "catch_up: id missing or wrong speaker"
    elif t == "reply_suggestions":
        if not all(isinstance(o, str) and o.strip() and len(o.split()) <= 15 for o in ev["options"]):
            return "reply_suggestions: bad option"
    else:
        return f"unknown event type {t!r}"
    return None


def verbatim_guard(events: list[dict], history: list[Utterance]) -> list[str]:
    """All violations across events ([] = clean). Utterance text is never a field of any event."""
    by_id = {u.id: u for u in history}
    return [v for e in events if (v := check_event(e, by_id))]
