"""노션 '할 일 관리' ↔ team CSV 동기화 공통: 칸 맞추기 · 마지막 동기화 스냅샷.

스냅샷(data/notion_sync_state.json) = 지난 배치가 끝났을 때 양쪽이 같았던 값.
  - CSV 만 바뀜  → CSV 값을 노션으로 (plan_csv_to_notion.py)
  - 노션만 바뀜 → 노션 값을 CSV 로 (sync_notion_tasks.py)
  - 둘 다 바뀜  → 노션이 이겨요 (정본)
"""

from __future__ import annotations

import json
from pathlib import Path

FIELDS = ["할 일", "직군", "담당자", "상태", "시작", "마감", "예상 시간", "프로젝트"]


def option_id(value) -> str:
    """노션 선택지 '이름 · 아이디(번호)' 에서 · 뒤만."""
    return str(value or "").split("·")[-1].strip()


def snap_value(snap: dict, field: str):
    """스냅샷에 없는 칸(나중에 생긴 '프로젝트' 등)은 빈 값으로 봐요."""
    return snap.get(field, None if field == "예상 시간" else "")


def norm_value(field: str, value):
    if field == "예상 시간":
        try:
            return float(value) if value not in (None, "") else None
        except ValueError:
            return None
    return str(value or "").strip()[:10] if field in ("시작", "마감") else str(value or "").strip()


def from_csv(task: dict) -> dict:
    return {f: norm_value(f, task.get(f)) for f in FIELDS}


def from_notion(row: dict) -> dict:
    start = str(row.get("date:기간:start") or "")[:10]
    return {
        "할 일": norm_value("할 일", row.get("할 일")),
        "직군": norm_value("직군", row.get("직군")),
        "담당자": str(row.get("담당") or "").split("·")[-1].strip(),
        "상태": norm_value("상태", row.get("상태")),
        "시작": start,
        "마감": str(row.get("date:기간:end") or "")[:10] or start,
        "예상 시간": norm_value("예상 시간", row.get("예상 공수")),
        "프로젝트": option_id(row.get("프로젝트")),
    }


def state_path(data_dir: Path) -> Path:
    return data_dir / "notion_sync_state.json"


def load_state(data_dir: Path) -> dict:
    p = state_path(data_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(data_dir: Path, tasks: list[dict]) -> None:
    state = {t["번호"]: from_csv(t) for t in tasks}
    state_path(data_dir).write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def to_notion_props(fields: dict, members: dict, projects: dict | None = None) -> dict:
    """정규화된 칸 → 노션 속성 (있는 칸만). projects = {번호: 이름} → '이름 · 번호' 선택지."""
    props = {}
    if "할 일" in fields:
        props["할 일"] = fields["할 일"]
    if "직군" in fields:
        props["직군"] = fields["직군"]
    if "담당자" in fields:
        mid = fields["담당자"]
        props["담당"] = f"{members[mid]} · {mid}" if mid in members else mid
    if "상태" in fields:
        props["상태"] = fields["상태"]
    if "시작" in fields or "마감" in fields:
        start = fields.get("시작") or fields.get("마감")
        props["date:기간:start"] = start
        props["date:기간:end"] = fields.get("마감") or start
        props["date:기간:is_datetime"] = 0
    if "예상 시간" in fields and fields["예상 시간"] is not None:
        props["예상 공수"] = fields["예상 시간"]
    if fields.get("프로젝트"):
        num = fields["프로젝트"]
        props["프로젝트"] = f"{(projects or {})[num]} · {num}" if num in (projects or {}) else num
    return props
