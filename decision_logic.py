from __future__ import annotations

from typing import Any

import streamlit as st

from state import DECISIONS_KEY, get_decisions
from track_search import result_for_index

def get_selected_candidates() -> list[dict[str, Any]]:
    decisions = get_decisions()
    selected: list[dict[str, Any]] = []

    for decision in decisions.values():
        if decision.get("decision") == "selected" and decision.get("candidate"):
            selected.append(decision["candidate"])

    return selected

def save_selected_candidate(index: int, candidate_index: int) -> None:
    result = result_for_index(index)
    if not result:
        return

    candidates = result.get("ranked_candidates", [])
    if candidate_index >= len(candidates):
        return

    candidate = candidates[candidate_index]
    decisions = get_decisions()
    decisions[index] = {
        "decision": "selected",
        "candidate_index": candidate_index,
        "candidate": candidate,
    }
    st.session_state[DECISIONS_KEY] = decisions


def mark_track(index: int, decision_type: str) -> None:
    decisions = get_decisions()
    decisions[index] = {"decision": decision_type}
    st.session_state[DECISIONS_KEY] = decisions


def clear_decision(index: int) -> None:
    decisions = get_decisions()
    decisions.pop(index, None)
    st.session_state[DECISIONS_KEY] = decisions


def decision_for_index(index: int) -> dict[str, Any] | None:
    return get_decisions().get(index)


def status_for_index(index: int) -> str:
    decision = decision_for_index(index)
    result = result_for_index(index)

    if decision:
        decision_type = decision.get("decision")
        if decision_type == "selected":
            return "selected"
        if decision_type == "skip":
            return "skipped"
        if decision_type == "not_found":
            return "marked not found"

    if result:
        result_status = result.get("status")
        if result_status == "error":
            return "error"
        if result_status == "found":
            return "searched"
        if result_status == "not_found":
            return "no hits"
        return "searched"

    return "pending"
