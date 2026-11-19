"""공개 범위 계산 — 누가 누구의 작업 기록 · 할 일 · 이슈를 볼 수 있나 (설계 문서 §5).

순수 함수만 있어요 (파일을 읽거나 쓰지 않아요). 표는 CSV 한 줄 = dict 목록이에요.
  scope_for(viewer, tables, day)  → 그 사람이 볼 수 있는 범위
  filter_tables(scope, tables)    → 범위대로 거른 표 (입력은 그대로 둬요)

viewer 가 '' 이면 공개 보기예요: 제한 항목(작업 기록 · 체크인 · 회의 · 할 일 · 이슈 · 기간 연장)이 0개예요.
출퇴근 · 근무 시간 · 상태 · 휴가 · 팀원 명단 · 프로젝트 배치는 누구나 봐요.
"""

from __future__ import annotations

import re

PUBLIC = ""
ITEMS = ("작업 기록", "할 일", "이슈")
FILTERED = ("tasks", "issues", "worklog", "checkins", "meetings", "extensions", "access")


def _active(row: dict, day: str) -> bool:
    return row.get("시작", "") <= day and (not row.get("종료") or day <= row["종료"])


def _sort_ids(ids) -> list[str]:
    return sorted(ids, key=lambda x: (len(x), x))


def scope_for(viewer: str, t: dict[str, list[dict]], day: str) -> dict:
    """viewer 가 그날(day) 볼 수 있는 범위."""
    running = {p["번호"] for p in t.get("projects", []) if p.get("상태") == "진행"}
    member_projects: dict[str, list[str]] = {}
    for m in t.get("members", []):
        member_projects[m["아이디"]] = []
    for a in t.get("project_members", []):
        if a["프로젝트"] in running and _active(a, day):
            member_projects.setdefault(a["아이디"], [])
            if a["프로젝트"] not in member_projects[a["아이디"]]:
                member_projects[a["아이디"]].append(a["프로젝트"])
    member_projects = {k: _sort_ids(v) for k, v in member_projects.items()}
    mine = member_projects.get(viewer, []) if viewer else []
    co = sorted(m for m, ps in member_projects.items() if m != viewer and set(ps) & set(mine))
    grants: dict[str, list[str]] = {it: [] for it in ITEMS}
    if viewer:
        for g in t.get("access", []):
            if g.get("보는 사람") == viewer and g.get("상태") == "유효" and g.get("항목") in grants:
                if g["대상"] not in grants[g["항목"]]:
                    grants[g["항목"]].append(g["대상"])
    scope = {"member": viewer, "projects": mine, "memberProjects": member_projects, "coPeople": co,
             "grants": grants, "taskIds": [], "issueIds": []}
    scope["taskIds"] = [x["번호"] for x in t.get("tasks", []) if _see_task(scope, x)]
    scope["issueIds"] = [x["번호"] for x in t.get("issues", []) if _see_issue(scope, x)]
    return scope


def _granted(scope: dict, item: str, person: str) -> bool:
    g = scope["grants"].get(item, [])
    return bool(person) and (person in g or "전원" in g)


def _see_task(scope: dict, row: dict) -> bool:
    v = scope["member"]
    if not v:
        return False
    owner = row.get("담당자", "")
    return (row.get("프로젝트", "") in scope["projects"]) or owner == v or _granted(scope, "할 일", owner)


def _see_issue(scope: dict, row: dict) -> bool:
    v = scope["member"]
    if not v:
        return False
    owner = row.get("담당자", "")
    return (row.get("프로젝트", "") in scope["projects"] or owner == v or row.get("보고자") == v
            or _granted(scope, "이슈", owner))


def _see_person_logs(scope: dict, person: str) -> bool:
    """할 일에 묶이지 않은 기록 · 체크인: 본인, 같은 프로젝트 동료, 관리자가 연 사람."""
    v = scope["member"]
    return bool(v) and (person == v or person in scope["coPeople"] or _granted(scope, "작업 기록", person))


def _see_log(scope: dict, row: dict, task_project: dict[str, str]) -> bool:
    v, author = scope["member"], row.get("담당자", "")
    if not v:
        return False
    if author == v or _granted(scope, "작업 기록", author):
        return True
    task = row.get("할 일 번호", "")
    if task:
        proj = task_project.get(task, "")
        return bool(proj) and proj in scope["projects"] and proj in scope["memberProjects"].get(author, [])
    return author in scope["coPeople"]


def _attendees(row: dict) -> list[str]:
    return [a for a in re.split(r"[,\s]+", row.get("참석자", "")) if a]


def filter_tables(scope: dict, t: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """범위대로 거른 새 표. 거르지 않는 표는 그대로 넘겨요."""
    v = scope["member"]
    tasks_ok = set(scope["taskIds"])
    issues_ok = set(scope["issueIds"])
    task_project = {x["번호"]: x.get("프로젝트", "") for x in t.get("tasks", [])}
    out = {k: list(rows) for k, rows in t.items() if k not in FILTERED}
    out["tasks"] = [dict(x) for x in t.get("tasks", []) if x["번호"] in tasks_ok]
    out["issues"] = [dict(x) for x in t.get("issues", []) if x["번호"] in issues_ok]
    out["worklog"] = [dict(x) for x in t.get("worklog", []) if _see_log(scope, x, task_project)]
    out["checkins"] = [dict(x) for x in t.get("checkins", []) if _see_person_logs(scope, x.get("아이디", ""))]
    out["meetings"] = [dict(x) for x in t.get("meetings", [])
                       if v and any(a == v or _see_person_logs(scope, a) for a in _attendees(x))]
    exts = []
    for e in t.get("extensions", []):
        if e.get("할 일 번호") in tasks_ok:
            e = dict(e)
            if e.get("신청자") != v:
                e["사유"] = ""
            exts.append(e)
    out["extensions"] = exts
    out["access"] = [dict(g) for g in t.get("access", []) if v and g.get("보는 사람") == v]
    return out
