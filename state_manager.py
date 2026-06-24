import json
import os
from typing import Set, Dict, Any

STATE_FILE = os.path.join(os.path.dirname(__file__), "estado.json")


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_thread_ids": [], "thread_last_modified": {}}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_processed_ids(state: Dict[str, Any]) -> Set[str]:
    return set(state.get("processed_thread_ids", []))


def get_thread_history_id(state: Dict[str, Any], thread_id: str) -> str | None:
    return state.get("thread_last_modified", {}).get(thread_id)


def mark_thread_processed(state: Dict[str, Any], thread_id: str, history_id: str) -> None:
    processed = set(state.get("processed_thread_ids", []))
    processed.add(thread_id)
    state["processed_thread_ids"] = list(processed)
    state.setdefault("thread_last_modified", {})[thread_id] = history_id
