"""노션 '할 일 관리' → team CSV 맞추기 (배치).

    uv run python sync_notion_tasks.py <노션 행 JSON 파일> [--dry-run]

입력: 노션 MCP notion-query-data-sources(mode=rows) 결과의 results 배열 (또는 {"results": [...]})
하는 일 (TEAM_ME = PO 로 실행):
  - 번호가 있는 행: 이름 · 직군 · 담당 · 기간 · 예상 공수가 다르면 update_task, 상태가 다르면 update_task_status
  - 번호가 빈 행: add_task 로 새 할 일 → 결과의 "새 번호" 를 노션 '번호' 칸에 다시 적어야 해요
출력: JSON {"changed": [...], "created": [{"url", "번호"}], "skipped": [...]}  (바뀐 게 없으면 changed · created 가 비어 있어요)
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import team_server as s  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from notion_sync_common import from_csv, from_notion, load_state, save_state, snap_value  # noqa: E402


def member_id(option: str) -> str:
    return str(option or "").split("·")[-1].strip()


def as_task(row: dict) -> dict:
    start = str(row.get("date:기간:start") or "")[:10]
    due = str(row.get("date:기간:end") or "")[:10] or start
    est = row.get("예상 공수")
    return {
        "번호": str(row.get("번호") or "").strip(),
        "할 일": str(row.get("할 일") or "").strip(),
        "직군": str(row.get("직군") or "").strip(),
        "담당자": member_id(row.get("담당")),
        "상태": str(row.get("상태") or "").strip(),
        "시작": start,
        "마감": due,
        "예상 시간": None if est in (None, "") else float(est),
        "프로젝트": member_id(row.get("프로젝트")),
        "url": row.get("url", ""),
    }


def same_number(a: str, b) -> bool:
    try:
        return float(a or 0) == float(b or 0)
    except ValueError:
        return False


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows = data.get("results", data) if isinstance(data, dict) else data
    dry = "--dry-run" in sys.argv
    me = os.environ.get("TEAM_ME", "")
    current = {t["번호"]: t for t in s.list_tasks()["할 일"]}
    state = load_state(s.data_dir())
    out = {"changed": [], "created": [], "skipped": []}
    for row in rows:
        n = as_task(row)
        if not n["할 일"] or not n["마감"] or not n["담당자"]:
            out["skipped"].append({"url": n["url"], "이유": "이름 · 기간 · 담당 중 빈 칸이 있어요"})
            continue
        try:
            if not n["번호"]:
                if dry:
                    out["created"].append({"url": n["url"], "번호": "(새 번호)", "할 일": n["할 일"]})
                    continue
                t = s.add_task(n["할 일"], n["직군"], n["담당자"], n["마감"], start=n["시작"],
                               estimate_hours=n["예상 시간"] or 0, project=n["프로젝트"])["할 일"]
                if n["상태"] and n["상태"] != "할 일":
                    s.update_task_status(t["번호"], n["상태"])
                out["created"].append({"url": n["url"], "번호": t["번호"], "할 일": t["할 일"]})
                continue
            cur = current.get(n["번호"])
            if not cur:
                out["skipped"].append({"url": n["url"], "이유": f"CSV 에 할 일 #{n['번호']} 가 없어요"})
                continue
            # 노션 칸이 지난 동기화 값과 같으면(노션은 안 바뀜) 건드리지 않아요 → CSV 쪽 변경은 plan_csv_to_notion 이 노션으로 보내요
            snap = state.get(n["번호"])
            nf, cf = from_notion(row), from_csv(cur)

            def notion_changed(field: str) -> bool:
                return nf[field] != cf[field] and (snap is None or nf[field] != snap_value(snap, field))

            diff = {}
            if nf["할 일"] and notion_changed("할 일"):
                diff["title"] = nf["할 일"]
            if nf["직군"] and notion_changed("직군"):
                diff["role"] = nf["직군"]
            if nf["담당자"] and notion_changed("담당자"):
                diff["assignee"] = nf["담당자"]
            if nf["시작"] and notion_changed("시작"):
                diff["start"] = nf["시작"]
            if nf["마감"] and notion_changed("마감"):
                diff["due"] = nf["마감"]
            if nf["프로젝트"] and notion_changed("프로젝트"):
                diff["project"] = nf["프로젝트"]
            if nf["예상 시간"] is not None and notion_changed("예상 시간") and not same_number(cur.get("예상 시간"), nf["예상 시간"]):
                diff["estimate_hours"] = nf["예상 시간"]
            status = nf["상태"] if nf["상태"] and notion_changed("상태") else ""
            if not diff and not status:
                continue
            if not dry:
                if diff:
                    s.update_task(n["번호"], me, **diff)
                if status:
                    s.update_task_status(n["번호"], status)
            out["changed"].append({"번호": n["번호"], **diff, **({"status": status} if status else {})})
        except ToolError as e:
            out["skipped"].append({"url": n["url"], "번호": n["번호"], "이유": str(e)})
    if not dry and "--no-state" not in sys.argv:
        save_state(s.data_dir(), s.list_tasks()["할 일"])  # 이번에 맞춘 값 = 다음 비교 기준
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
