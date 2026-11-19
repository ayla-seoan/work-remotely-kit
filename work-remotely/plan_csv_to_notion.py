"""team CSV(Claude Code 로 바꾼 할 일) → 노션 '할 일 관리' 에 보낼 목록 (배치용).

    uv run python plan_csv_to_notion.py <노션 rows JSON>

- CSV 에만 있는 할 일 → 노션에 번호와 함께 새로 만들기
- 노션에도 있는 할 일 → 지난 동기화 뒤 CSV 에서만 바뀐 칸만 노션으로 (노션도 바뀐 칸은 건드리지 않아요: 노션이 정본)
- 스냅샷이 없는 첫 실행은 아무것도 보내지 않아요 (노션 → CSV 가 먼저 맞춰요)
출력: {"actions": [{"op": "update", "page_id", "번호", "properties"} | {"op": "create", "번호", "properties"}]}
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from notion_sync_common import FIELDS, from_csv, from_notion, load_state, snap_value, to_notion_props  # noqa: E402


def plan(notion_rows: list, tasks: list, state: dict, members: dict, projects: dict | None = None) -> dict:
    by_number = {str(r.get("번호") or "").strip(): r for r in notion_rows if str(r.get("번호") or "").strip()}
    actions = []
    if not state:
        return {"actions": [], "note": "스냅샷이 없어서 첫 실행은 노션 → CSV 만 해요"}
    for t in tasks:
        num, cur = t["번호"], from_csv(t)
        row = by_number.get(num)
        if row is None:
            if num in state:
                continue  # 노션에서 지운 할 일은 다시 만들지 않아요
            props = to_notion_props(cur, members, projects)
            props["번호"] = num
            actions.append({"op": "create", "번호": num, "properties": props})
            continue
        snap = state.get(num)
        if snap is None:
            continue
        notion = from_notion(row)
        changed = {f: cur[f] for f in FIELDS
                   if cur[f] != snap_value(snap, f) and notion[f] == snap_value(snap, f) and cur[f] != notion[f]}
        if changed:
            actions.append({"op": "update", "page_id": row.get("url"), "번호": num, "properties": to_notion_props(changed, members, projects)})
    return {"actions": actions}


def read_csv(path: Path) -> list:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data_dir = Path(os.environ.get("TEAM_DATA_DIR") or HERE / "data")
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows = raw.get("results", raw) if isinstance(raw, dict) else raw
    members = {m["아이디"]: m["이름"] for m in read_csv(data_dir / "members.csv")}
    pfile = data_dir / "projects.csv"
    projects = {p["번호"]: p["이름"] for p in read_csv(pfile)} if pfile.exists() else {}
    print(json.dumps(plan(rows, read_csv(data_dir / "tasks.csv"), load_state(data_dir), members, projects), ensure_ascii=False))
