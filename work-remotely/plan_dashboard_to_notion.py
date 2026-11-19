"""대시보드(공유 저장소)에서 고친 할 일 → 노션 '할 일 관리' 에 보낼 목록 만들기 (배치용).

    uv run python plan_dashboard_to_notion.py <입력 JSON>

입력 JSON:
  {"taskEdits": {"<할 일 번호 또는 새 t…>": {title, role, assignee, start, due, estimate, project, at}},
   "events":    [{id, type: "task_status", task, status, at, ...}, ...],   # 다른 type 은 무시
   "done":      ["task:<id>", "<event id>", ...],                          # sync/state.done
   "notion":    [노션 rows 결과 ...],
   "members":   {"<아이디>": "<이름>"},
   "projects":  {"<번호>": "<이름>"}}                                  # 화면에서 고른 프로젝트 → 노션 선택지
출력 JSON:
  {"actions": [{"op": "update", "page_id": url, "properties": {...}} | {"op": "create", "properties": {...}}],
   "done": ["task:t…", "e…"],   # 노션에 보낸 뒤 sync/state.done 에 더할 것
   "skipped": [...]}
노션에 이미 같은 값이 있으면 보내지 않아요 (두 번 돌려도 같은 결과).
"""

import json
import sys
from pathlib import Path


def option(member_id: str, members: dict) -> str:
    return f"{members[member_id]} · {member_id}" if member_id in members else member_id


def notion_props(edit: dict, members: dict, projects: dict | None = None) -> dict:
    props = {}
    if edit.get("title"):
        props["할 일"] = edit["title"]
    if edit.get("role"):
        props["직군"] = edit["role"]
    if edit.get("assignee"):
        props["담당"] = option(edit["assignee"], members)
    if edit.get("start") or edit.get("due"):
        start = edit.get("start") or edit.get("due")
        props["date:기간:start"] = start
        props["date:기간:end"] = edit.get("due") or start
        props["date:기간:is_datetime"] = 0
    if edit.get("estimate") not in (None, ""):
        props["예상 공수"] = float(edit["estimate"])
    if edit.get("status"):
        props["상태"] = edit["status"]
    if edit.get("project"):
        num = str(edit["project"])
        props["프로젝트"] = f"{(projects or {})[num]} · {num}" if num in (projects or {}) else num
    return props


def differs(props: dict, row: dict) -> dict:
    """노션 행과 다른 칸만 남겨요."""
    out = {}
    for k, v in props.items():
        cur = row.get(k)
        if k == "예상 공수":
            if cur in (None, "") or float(cur) != float(v):
                out[k] = v
        elif k.startswith("date:기간:"):
            if k == "date:기간:is_datetime":
                continue
            if str(cur or "")[:10] != str(v):
                out.update({kk: props[kk] for kk in props if kk.startswith("date:기간:")})
        elif str(cur or "") != str(v):
            out[k] = v
    return out


def plan(data: dict) -> dict:
    members = data.get("members", {})
    projects = data.get("projects", {})
    done = set(data.get("done", []))
    rows = data.get("notion", [])
    by_number = {str(r.get("번호") or "").strip(): r for r in rows if str(r.get("번호") or "").strip()}
    actions, new_done, skipped = [], [], []

    # 할 일마다 최신 상태 이벤트
    latest, all_ids = {}, {}
    for e in sorted(data.get("events", []), key=lambda e: str(e.get("at", ""))):
        if e.get("type") == "task_status" and e.get("id") not in done and e.get("task"):
            latest[e["task"]] = e
            all_ids.setdefault(e["task"], []).append(e["id"])  # 묻힌 예전 상태도 같이 '옮김' 처리 (되돌아가지 않게)

    edits = {k: v for k, v in data.get("taskEdits", {}).items() if f"task:{k}" not in done}
    for task_id in sorted(set(edits) | set(latest)):
        edit = dict(edits.get(task_id, {}))
        ev = latest.get(task_id)
        if ev:
            edit["status"] = ev["status"]
        ids = ([f"task:{task_id}"] if task_id in edits else []) + all_ids.get(task_id, [])
        props = notion_props(edit, members, projects)
        if not props:
            new_done += ids
            continue
        row = by_number.get(task_id)
        if row:
            change = differs(props, row)
            if change:
                actions.append({"op": "update", "page_id": row.get("url"), "번호": task_id, "properties": change})
            new_done += ids
        elif task_id in edits and not task_id.isdigit():
            # 대시보드에서 새로 만든 할 일 → 노션에 번호 없이 추가 (다음 노션→CSV 단계가 번호를 매겨요)
            if not (props.get("할 일") and props.get("date:기간:start") and props.get("담당")):
                skipped.append({"id": task_id, "이유": "이름 · 기간 · 담당 중 빈 칸이 있어요"})
                continue
            actions.append({"op": "create", "id": task_id, "properties": {**props, "상태": props.get("상태", "할 일")}})
            new_done += ids
        else:
            skipped.append({"id": task_id, "이유": f"노션에 번호 {task_id} 인 행이 없어요"})
    return {"actions": actions, "done": new_done, "skipped": skipped}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(plan(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))), ensure_ascii=False))
