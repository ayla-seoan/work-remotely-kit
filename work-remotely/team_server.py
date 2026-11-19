"""team — 팀원 · 할 일 · 이슈 · 작업 기록을 관리하는 MCP 서버 (mcp 2.x · stdio).

데이터는 data/ 폴더의 CSV 4개에 있어요. 사람이 엑셀로 열어 봐도 되고, git 으로 이력이 남아요.
  members.csv  팀원        (아이디, 이름, 직군, 역할, 상태)
  tasks.csv    할 일       (번호, 할 일, 직군, 담당자, 상태, 마감)
  issues.csv   이슈        (번호, 제목, 내용, 심각도, 상태, 담당자, 보고자, 관련 할 일, 생성일, 수정일, 메모)
  worklog.csv  작업 기록   (번호, 날짜, 담당자, 할 일 번호, 내용, 시간)

안전 규칙
  - 지우기 도구는 없어요. 이슈는 '해결' 로 바꾸고, 할 일은 '완료' 로 바꿔요.
  - 환경변수 TEAM_READONLY=1 이면 쓰기 도구를 아예 등록하지 않아요 (읽기 전용 모드).
  - 담당자 · 상태 · 날짜는 정해진 값만 받아요. 틀리면 에러 메시지로 고칠 방법을 알려 줘요.

환경변수
  TEAM_DATA_DIR  데이터 폴더 (기본: 이 파일 옆 data/)
  TEAM_READONLY  1 이면 읽기 전용
  TEAM_TODAY     오늘 날짜 고정 (YYYY-MM-DD, 테스트용)
  TEAM_NOW       지금 시각 고정 (HH:MM, 테스트용)

재택 근무 (없으면 처음 쓸 때 만들어져요)
  attendance.csv 출퇴근      (번호, 날짜, 아이디, 출근, 퇴근, 근무지, 메모)
  leaves.csv     휴가 · 부재 (번호, 신청자, 종류, 시작, 끝, 사유, 상태, 검토자, 검토 메모, 신청일, 검토일)
  presence.csv   실시간 상태 (아이디, 상태, 메모, 바뀐 시각) — 사람마다 한 줄
  checkins.csv   데일리 체크인 (번호, 날짜, 아이디, 어제, 오늘, 막힘)

프로젝트 · 공개 범위 (쓰기는 PO 만)
  projects.csv        프로젝트   (번호, 이름, 시작, 종료, 담당 관리자, 상태, 만든 날)
  project_members.csv 배치       (번호, 프로젝트, 아이디, 시작, 종료, 메모) — 종료가 비면 계속
  access.csv          공개 범위  (번호, 보는 사람, 대상, 항목, 부여자, 날짜, 상태) — 회수는 상태만 바꿔요
  tasks.csv · issues.csv 의 '프로젝트' 칸 = 프로젝트 번호
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # 예상한 실패 → AI 가 메시지를 그대로 읽어요
from mcp.types import ToolAnnotations

# ── 정해진 값 ────────────────────────────────────────────────
TASK_STATUSES = ["할 일", "진행 중", "완료"]
ISSUE_STATUSES = ["열림", "진행 중", "해결", "보류"]
ISSUE_OPEN = {"열림", "진행 중", "보류"}  # '해결' 이 아니면 아직 남은 이슈
SEVERITIES = ["긴급", "높음", "보통", "낮음"]  # 앞쪽일수록 급함

FIELDS = {
    "members": ["아이디", "이름", "직군", "역할", "상태"],
    "tasks": ["번호", "할 일", "직군", "담당자", "상태", "시작", "마감", "기준 마감", "예상 시간", "프로젝트"],
    "extensions": ["번호", "할 일 번호", "신청자", "기존 시작", "요청 시작", "기존 마감", "요청 마감", "사유", "상태",
                   "검토자", "검토 메모", "신청일", "검토일"],
    "issues": ["번호", "제목", "내용", "심각도", "상태", "담당자", "보고자", "관련 할 일", "생성일", "수정일", "메모", "프로젝트"],
    "worklog": ["번호", "날짜", "담당자", "할 일 번호", "내용", "시간", "링크"],
    "meetings": ["번호", "날짜", "시작", "끝", "제목", "참석자", "결정", "링크", "기록자"],
    # 재택 근무
    "attendance": ["번호", "날짜", "아이디", "출근", "퇴근", "근무지", "메모"],
    "leaves": ["번호", "신청자", "종류", "시작", "끝", "사유", "상태", "검토자", "검토 메모", "신청일", "검토일"],
    "presence": ["아이디", "상태", "메모", "바뀐 시각"],
    "checkins": ["번호", "날짜", "아이디", "어제", "오늘", "막힘"],
    # 프로젝트 · 배치 · 공개 범위
    "projects": ["번호", "이름", "시작", "종료", "담당 관리자", "상태", "만든 날"],
    "project_members": ["번호", "프로젝트", "아이디", "시작", "종료", "메모"],
    "access": ["번호", "보는 사람", "대상", "항목", "부여자", "날짜", "상태"],
}
PROJECT_STATUSES = ["진행", "종료"]
ACCESS_ITEMS = ["작업 기록", "할 일", "이슈"]

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


# ── 파일 읽기 · 쓰기 ─────────────────────────────────────────
def data_dir() -> Path:
    """데이터 폴더. 호출할 때마다 환경변수를 다시 읽어서 테스트에서 바꾸기 쉬워요."""
    custom = os.environ.get("TEAM_DATA_DIR")
    return Path(custom) if custom else Path(__file__).resolve().parent / "data"


def today() -> date:
    fixed = os.environ.get("TEAM_TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()


def now_hhmm() -> str:
    """지금 시각 HH:MM. TEAM_NOW 로 고정할 수 있어요 (테스트용)."""
    fixed = os.environ.get("TEAM_NOW", "").strip()
    return fixed if fixed else datetime.now().strftime("%H:%M")


def _read(table: str) -> list[dict[str, str]]:
    path = data_dir() / f"{table}.csv"
    if not path.exists():
        return []
    # utf-8-sig: 엑셀이 붙이는 BOM 이 있어도 첫 칸 이름이 깨지지 않아요.
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


def _write(table: str, rows: list[dict[str, str]]) -> None:
    """임시 파일에 다 쓴 뒤 바꿔치기 → 중간에 멈춰도 원래 파일이 망가지지 않아요."""
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS[table])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS[table]})
    os.replace(tmp, folder / f"{table}.csv")


def _next_id(rows: list[dict[str, str]]) -> str:
    nums = [int(r["번호"]) for r in rows if r.get("번호", "").isdigit()]
    return str(max(nums, default=0) + 1)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ── 검증 도우미 ──────────────────────────────────────────────
def _member_ids() -> set[str]:
    return {m["아이디"] for m in _read("members")}


def _check_member(member_id: str, label: str = "담당자") -> None:
    ids = _member_ids()
    if member_id not in ids:
        raise ToolError(f"{label} '{member_id}' 는 팀원 목록에 없어요. 가능한 아이디: {', '.join(sorted(ids))}")


def _is_po(member_id: str) -> bool:
    return any(m["아이디"] == member_id and m["직군"] == "PO" for m in _read("members"))


def me() -> str:
    """TEAM_ME 환경변수 = 이 서버를 쓰는 사람의 팀원 아이디 (없으면 '')."""
    return os.environ.get("TEAM_ME", "").strip()


def _check_self(member_id: str, label: str) -> None:
    """TEAM_ME 가 정해져 있으면, 기록 · 요청 · 승인은 본인 이름으로만 할 수 있어요."""
    mine = me()
    if mine and member_id != mine:
        raise ToolError(f"{label} '{member_id}' 는 이 컴퓨터의 사용자({mine}) 가 아니에요. 다른 사람 이름으로는 할 수 없어요. "
                        f"본인 아이디 '{mine}' 로 다시 해 주세요.")


def _notion_hint(task: dict) -> dict:
    """이 할 일을 노션 '할 일 관리' 에 그대로 맞추는 데 필요한 값. 결과에 붙여서 Claude 가 바로 노션에 반영하게 해요."""
    from notion_sync_common import from_csv, to_notion_props  # 같은 폴더의 공통 모듈
    names = {m["아이디"]: m["이름"] for m in _read("members")}
    projects = {p["번호"]: p["이름"] for p in _read("projects")}
    props = to_notion_props(from_csv(task), names, projects)
    props["번호"] = task["번호"]
    db = settings().get("할 일 노션 DB", "")
    return {
        "번호": task["번호"], "properties": props, "노션 DB": db,
        "할 일": "노션 '할 일 관리' 에서 '번호' 가 같은 행을 notion-update-page(update_properties) 로 고치고, 없으면 notion-create-pages 로 만들어요. "
                "바로 반영하면 대시보드에 30초 안에 보여요 (안 해도 5분 배치가 맞춰요).",
    }


def _in_project(row: dict[str, str], project: str) -> bool:
    return not project or row.get("프로젝트", "") == project


def _resolve_project(project: str, *people: str) -> str:
    """새 할 일 · 이슈의 프로젝트. 비우면 담당자 · 보고자(people), 그다음 나(TEAM_ME) 순서로
    현재 프로젝트가 딱 하나인 사람의 것을 써요. 프로젝트가 아직 없으면 ''."""
    project = str(project or "").strip().lstrip("#")
    if project:
        return _find_project(project)["번호"]
    if not _read("projects"):
        return ""
    mine: list[str] = []
    for person in [*people, me()]:
        if not person:
            continue
        theirs = current_projects(person)
        if len(theirs) == 1:
            return theirs[0]
        mine = mine or theirs
    choices = ", ".join(f"{p['번호']}({p['이름']})" for p in _read("projects") if not mine or p["번호"] in mine)
    raise ToolError(f"프로젝트를 정해 주세요 (project 인자). 가능한 번호: {choices}")


def _check_choice(value: str, choices: list[str], label: str) -> None:
    if value not in choices:
        raise ToolError(f"{label} '{value}' 는 쓸 수 없어요. 가능한 값: {', '.join(choices)}")


def _find(rows: list[dict[str, str]], row_id: str, label: str) -> dict[str, str]:
    for row in rows:
        if row["번호"] == str(row_id).lstrip("#"):
            return row
    raise ToolError(f"{label} #{row_id} 를 찾을 수 없어요.")


def _ratio(done: int, total: int) -> str:
    return f"{done}/{total} ({round(done / total * 100) if total else 0}%)"


def _sev_rank(issue: dict[str, str]) -> int:
    return SEVERITIES.index(issue["심각도"]) if issue["심각도"] in SEVERITIES else len(SEVERITIES)


# ── 서버 ─────────────────────────────────────────────────────
mcp = MCPServer(
    name="team",
    title="팀 · 프로젝트 관리",
    version="0.2.0",
    instructions=(
        "팀원 · 할 일 · 이슈 · 작업 기록을 관리하는 서버예요. "
        "먼저 team_dashboard 나 list_members 로 전체를 보고, 사람 한 명은 member_status 로 보세요. "
        "재택 근무는 attendance(오늘 근무 현황) · work_hours · list_checkins · list_leaves · reminders 로 보세요. "
        "쓰기 도구(create_issue · update_issue · add_task · update_task_status · log_work · check_in · check_out · "
        "set_status · submit_checkin · request_leave · review_leave · create_project · update_project · "
        "assign_member · end_assignment · add_member · grant_access · revoke_access)는 "
        "사용자에게 내용을 먼저 보여 주고 승인받은 뒤에 부르세요. 지우기 도구는 없어요. "
        "데이터에 없는 사람 · 이슈 · 숫자는 지어내지 마세요. "
        "사용자가 '나' · '내' 라고 하면 먼저 whoami 로 누구인지 확인하고 그 아이디를 쓰세요."
    ),
)


# ── 읽기 도구 ────────────────────────────────────────────────
def team_dashboard(project: str = "") -> dict[str, Any]:
    """팀 전체 현황을 한 번에 보여 줘요. '팀 상황 어때?', '오늘 현황', '대시보드' 같은 질문에 가장 먼저 쓰세요.

    돌려주는 것: 전체 · 직군별 할 일 진행률, 심각도별 열린 이슈 수와 긴급 · 높음 이슈 목록,
    오늘 기준 3일 안 마감 · 마감 지난 할 일, 팀원별 남은 할 일 · 열린 이슈 · 최근 7일 작업 시간.
    project: 프로젝트 번호로 거르기 (진행률 · 이슈 · 할 일 수). 비우면 전체.
    """
    tasks = [x for x in _read("tasks") if _in_project(x, project)]
    issues = [x for x in _read("issues") if _in_project(x, project)]
    open_issues = [i for i in issues if i["상태"] in ISSUE_OPEN]
    return {
        "오늘": today().isoformat(),
        "진행률": progress(project),
        "열린 이슈 수": {s: sum(1 for i in open_issues if i["심각도"] == s) for s in SEVERITIES},
        "급한 이슈": [
            {k: i[k] for k in ("번호", "제목", "심각도", "상태", "담당자")}
            for i in sorted(open_issues, key=_sev_rank)
            if i["심각도"] in ("긴급", "높음")
        ],
        "마감 임박 · 지남": due_soon(3),
        "팀원별": list_members()["팀원"],
        "할 일 전체 수": len(tasks),
        "오늘 근무": attendance()["요약"],
        "오늘 회의": [{k: m[k] for k in ("번호", "시작", "끝", "제목")} for m in _read("meetings") if m["날짜"] == today().isoformat()],
        "담당 지정 필요": [
            {k: i[k] for k in ("번호", "제목", "심각도", "보고자")} for i in sorted(open_issues, key=_sev_rank) if not i["담당자"]
        ],
    }


def list_members(role: str = "") -> dict[str, Any]:
    """팀원 목록과 각자의 현재 부하(리소스)를 보여 줘요. '누가 바빠?', '팀원 누구 있어?', '개발자 목록' 등에 쓰세요.

    Args:
        role: 직군으로 거르기 (예: 개발, 디자인, PO, 마케팅). 비우면 전체.

    팀원마다: 아이디 · 이름 · 직군 · 역할 · 오늘 상태(근무 / 승인된 휴가 종류 등) · 오늘 일정(반차 · 외근) · 출근 · 퇴근 · 근무지 · 실시간 상태,
    남은 할 일 수(할 일 + 진행 중),
    진행 중 할 일 수, 맡은 열린 이슈 수, 최근 7일 작업 시간, 마지막 작업일.
    """
    tasks, issues, logs = _read("tasks"), _read("issues"), _read("worklog")
    since = today() - timedelta(days=7)
    day = today().isoformat()
    leaves = _read("leaves")
    att = {a["아이디"]: a for a in _read("attendance") if a["날짜"] == day}
    result = []
    for m in _read("members"):
        if role and m["직군"] != role:
            continue
        mid = m["아이디"]
        state, plan = _day_state(m, day, leaves)
        a = att.get(mid, {})
        my_tasks = [t for t in tasks if t["담당자"] == mid]
        my_logs = [w for w in logs if w["담당자"] == mid]
        recent = [w for w in my_logs if (d := _parse_date(w["날짜"])) and d >= since]
        result.append({
            **m,
            "상태": state, "오늘 일정": plan,
            "출근": a.get("출근", ""), "퇴근": a.get("퇴근", ""), "근무지": a.get("근무지", ""),
            "실시간 상태": _presence_of(mid, day)["상태"] if a and not a.get("퇴근") else "",
            "남은 할 일": sum(1 for t in my_tasks if t["상태"] != "완료"),
            "진행 중": sum(1 for t in my_tasks if t["상태"] == "진행 중"),
            "열린 이슈": sum(1 for i in issues if i["담당자"] == mid and i["상태"] in ISSUE_OPEN),
            "최근 7일 작업 시간": round(sum(float(w["시간"] or 0) for w in recent), 1),
            "마지막 작업일": max((w["날짜"] for w in my_logs), default=""),
        })
    return {"팀원 수": len(result), "팀원": result}


def member_status(member_id: str, days: int = 7) -> dict[str, Any]:
    """팀원 한 명이 지금 무엇을 맡고 있고 최근에 무엇을 했는지 보여 줘요. '○○ 요즘 뭐 해?', '내 할 일', 스탠드업 준비에 쓰세요.

    Args:
        member_id: 팀원 아이디 (members.csv 의 '아이디', 보통 깃허브 아이디).
        days: 최근 며칠의 작업 기록을 볼지 (기본 7일).
    """
    _check_member(member_id, "팀원")
    member = next(m for m in _read("members") if m["아이디"] == member_id)
    since = today() - timedelta(days=days)
    logs = [w for w in _read("worklog") if w["담당자"] == member_id and (d := _parse_date(w["날짜"])) and d >= since]
    return {
        "팀원": member,
        "할 일": list_tasks(assignee=member_id)["할 일"],
        "맡은 열린 이슈": list_issues(assignee=member_id)["이슈"],
        f"최근 {days}일 작업 기록": sorted(logs, key=lambda w: (w["날짜"], int(w["번호"]) if w["번호"].isdigit() else 0), reverse=True),
        f"최근 {days}일 작업 시간": round(sum(float(w["시간"] or 0) for w in logs), 1),
    }


def list_tasks(assignee: str = "", status: str = "", role: str = "", project: str = "") -> dict[str, Any]:
    """할 일 목록을 걸러서 보여 줘요. 빈 값은 '거르지 않음' 이에요.

    Args:
        assignee: 담당자 아이디. 없는 아이디면 빈 목록이에요 (에러 아님).
        status: 할 일 / 진행 중 / 완료 중 하나.
        role: 직군 (개발 · 디자인 · PO · 마케팅 등).
        project: 프로젝트 번호.
    """
    rows = [
        t for t in _read("tasks")
        if _in_project(t, project)
        and (not assignee or t["담당자"] == assignee)
        and (not status or t["상태"] == status)
        and (not role or t["직군"] == role)
    ]
    return {"개수": len(rows), "할 일": rows}


def progress(project: str = "") -> dict[str, Any]:
    """할 일 진행률(완료/전체)을 전체 · 직군별 · 담당자별로 보여 줘요. '얼마나 됐어?', '진행률' 질문에 쓰세요.
    project 를 주면 그 프로젝트 할 일만 세요."""
    tasks = [t for t in _read("tasks") if _in_project(t, project)]

    def group(key: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in sorted({t[key] for t in tasks}):
            mine = [t for t in tasks if t[key] == name]
            out[name or "(미배정)"] = _ratio(sum(t["상태"] == "완료" for t in mine), len(mine))
        return out

    return {
        "전체": _ratio(sum(t["상태"] == "완료" for t in tasks), len(tasks)),
        "직군별": group("직군"),
        "담당자별": group("담당자"),
    }


def list_issues(status: str = "", assignee: str = "", severity: str = "", project: str = "") -> dict[str, Any]:
    """팀 이슈(문제 · 막힌 것 · 버그 · 리스크)를 급한 순서로 보여 줘요.

    Args:
        status: 열림 / 진행 중 / 해결 / 보류. 비우면 '해결' 을 뺀 남은 이슈만 보여 줘요. 전부 보려면 '전체'.
        assignee: 담당자 아이디로 거르기.
        severity: 긴급 / 높음 / 보통 / 낮음.
        project: 프로젝트 번호.
    """
    rows = [i for i in _read("issues") if _in_project(i, project)]
    if status == "전체":
        pass
    elif status:
        rows = [i for i in rows if i["상태"] == status]
    else:
        rows = [i for i in rows if i["상태"] in ISSUE_OPEN]
    rows = [
        i for i in rows
        if (not assignee or i["담당자"] == assignee) and (not severity or i["심각도"] == severity)
    ]
    rows.sort(key=lambda i: (_sev_rank(i), i["생성일"]))
    return {"개수": len(rows), "이슈": rows}


def get_issue(issue_id: str) -> dict[str, Any]:
    """이슈 하나의 전체 내용과 메모(처리 이력)를 보여 줘요.

    Args:
        issue_id: 이슈 번호 (예: 3 또는 #3).
    """
    issue = _find(_read("issues"), issue_id, "이슈")
    related = issue["관련 할 일"]
    task = next((t for t in _read("tasks") if related and t["번호"] == related), None)
    return {"이슈": issue, "관련 할 일": task}


def due_soon(days: int = 3) -> dict[str, Any]:
    """오늘부터 N일 안에 마감인 할 일과 이미 마감이 지난 할 일을 보여 줘요 (완료된 건 빼요).

    Args:
        days: 며칠 안을 볼지 (기본 3일, 0 이면 오늘 마감만).
    """
    now, end = today(), today() + timedelta(days=days)
    soon, overdue = [], []
    for t in _read("tasks"):
        d = _parse_date(t["마감"])
        if t["상태"] == "완료" or d is None:
            continue
        if d < now:
            overdue.append({**t, "지난 일수": (now - d).days})
        elif d <= end:
            soon.append({**t, "남은 일수": (d - now).days})
    return {"기준일": now.isoformat(), f"{days}일 안 마감": soon, "마감 지남": overdue}


def work_log(member_id: str = "", days: int = 7) -> dict[str, Any]:
    """최근 작업 기록(누가 언제 무엇을 몇 시간 했는지)을 보여 줘요. 주간 보고 · 리소스 확인에 쓰세요.

    Args:
        member_id: 팀원 아이디로 거르기 (비우면 전체).
        days: 최근 며칠 (기본 7일).
    """
    since = today() - timedelta(days=days)
    rows = [
        w for w in _read("worklog")
        if (not member_id or w["담당자"] == member_id) and (d := _parse_date(w["날짜"])) and d >= since
    ]
    rows.sort(key=lambda w: (w["날짜"], int(w["번호"]) if w["번호"].isdigit() else 0), reverse=True)
    hours: dict[str, float] = {}
    for w in rows:
        hours[w["담당자"]] = round(hours.get(w["담당자"], 0) + float(w["시간"] or 0), 1)
    return {"기간": f"{since.isoformat()} ~ {today().isoformat()}", "사람별 시간": hours, "기록": rows}


# ── 쓰기 도구 (지우기 없음) ──────────────────────────────────
def create_issue(
    title: str, description: str, severity: str, reporter: str, assignee: str = "", task_id: str = "", project: str = ""
) -> dict[str, Any]:
    """새 이슈를 등록해요 (상태는 '열림' 으로 시작). 부르기 전에 내용을 사용자에게 보여 주고 승인받으세요.

    Args:
        title: 이슈 제목 (한 줄).
        description: 무엇이 문제인지 · 언제부터 · 원하는 결과.
        severity: 긴급 / 높음 / 보통 / 낮음.
        reporter: 등록하는 사람 아이디.
        assignee: 맡을 사람 아이디. 담당 지정은 PO 만 해요 — PO 가 아니면 비워 두세요 ('담당 지정 필요' 로 PO 에게 알려져요).
        task_id: 관련 할 일 번호 (있으면).
        project: 프로젝트 번호. 비우면 내 현재 프로젝트가 하나일 때 그것 (여러 개면 물어봐요).
    """
    if not title.strip():
        raise ToolError("제목이 비어 있어요.")
    _check_choice(severity, SEVERITIES, "심각도")
    _check_member(reporter, "보고자")
    _check_self(reporter, "보고자")
    if assignee:
        _check_member(assignee)
        if not _is_po(reporter):
            raise ToolError("담당 지정은 PO 가 해요. assignee 를 비우고 등록하면 PO 에게 '담당 지정 필요' 로 알려져요.")
    if task_id:
        _find(_read("tasks"), task_id, "할 일")
    project = _resolve_project(project, assignee, reporter)
    rows = _read("issues")
    now = today().isoformat()
    issue = {
        "번호": _next_id(rows), "제목": title.strip(), "내용": description.strip(), "심각도": severity,
        "상태": "열림", "담당자": assignee, "보고자": reporter, "관련 할 일": task_id.lstrip("#"),
        "생성일": now, "수정일": now, "메모": "", "프로젝트": project,
    }
    _write("issues", rows + [issue])
    tail = "" if assignee else " 담당자가 없어서 PO 의 담당 지정이 필요해요."
    return {"결과": f"이슈 #{issue['번호']} 를 등록했어요.{tail}", "이슈": issue}


def update_issue(issue_id: str, status: str = "", note: str = "") -> dict[str, Any]:
    """이슈의 상태를 바꾸거나 메모(처리 이력)를 덧붙여요. 이슈를 지우는 대신 '해결' 로 바꿔요.
    담당자 지정 · 변경은 PO 만 할 수 있어서 assign_issue 로 해요.

    Args:
        issue_id: 이슈 번호.
        status: 열림 / 진행 중 / 해결 / 보류 (비우면 그대로).
        note: 덧붙일 메모. 날짜와 함께 기존 메모 뒤에 쌓여요 (기존 메모는 지우지 않아요).
    """
    if not (status or note):
        raise ToolError("바꿀 것(status · note)을 하나 이상 주세요. 담당자는 PO 가 assign_issue 로 지정해요.")
    rows = _read("issues")
    issue = _find(rows, issue_id, "이슈")
    before = dict(issue)
    if status:
        _check_choice(status, ISSUE_STATUSES, "상태")
        issue["상태"] = status
    if note:
        entry = f"[{today().isoformat()}] {note.strip()}"
        issue["메모"] = f"{issue['메모']} / {entry}" if issue["메모"] else entry
    issue["수정일"] = today().isoformat()
    _write("issues", rows)
    changed = {k: f"{before[k]} → {issue[k]}" for k in ("상태",) if before[k] != issue[k]}
    return {"결과": f"이슈 #{issue['번호']} 를 고쳤어요.", "바뀐 것": changed, "이슈": issue}


def assign_issue(issue_id: str, assignee: str, assigner: str, note: str = "") -> dict[str, Any]:
    """PO 가 이슈의 담당자를 지정하거나 바꿔요. 담당자가 없는 이슈('담당 지정 필요')를 처리할 때 쓰세요.
    PO 직군만 쓸 수 있어요. 부르기 전에 사용자 승인을 받으세요.

    Args:
        issue_id: 이슈 번호.
        assignee: 맡길 팀원 아이디.
        assigner: 지정하는 PO 아이디.
        note: 메모 (선택). 이슈 메모에 '[날짜] 담당 지정: …' 으로 남아요.
    """
    _check_member(assigner, "지정자")
    _check_self(assigner, "지정자")
    if not _is_po(assigner):
        raise ToolError(f"'{assigner}' 는 PO 가 아니라서 담당을 지정할 수 없어요. 담당 지정은 PO 가 해요.")
    _check_member(assignee)
    rows = _read("issues")
    issue = _find(rows, issue_id, "이슈")
    if issue["상태"] == "해결":
        raise ToolError(f"이슈 #{issue['번호']} 는 이미 해결돼서 담당을 지정할 필요가 없어요.")
    before = issue["담당자"]
    issue["담당자"] = assignee
    entry = f"[{today().isoformat()}] 담당 지정: {before or '없음'} → {assignee}" + (f" ({note.strip()})" if note.strip() else "")
    issue["메모"] = f"{issue['메모']} / {entry}" if issue["메모"] else entry
    issue["수정일"] = today().isoformat()
    _write("issues", rows)
    return {"결과": f"이슈 #{issue['번호']} 담당: {before or '없음'} → {assignee}", "이슈": issue}


def add_task(
    title: str, role: str, assignee: str, due: str, start: str = "", estimate_hours: float = 0, project: str = ""
) -> dict[str, Any]:
    """새 할 일을 추가해요 (상태는 '할 일' 로 시작). 부르기 전에 사용자 승인을 받으세요.

    Args:
        title: 할 일 내용.
        role: 직군 (개발 · 디자인 · PO · 마케팅 등).
        assignee: 담당자 아이디.
        due: 마감일 YYYY-MM-DD. 처음 정한 마감은 '기준 마감' 으로도 저장돼요.
        start: 시작일 YYYY-MM-DD (비우면 오늘).
        estimate_hours: 예상 공수(시간). 0 이면 '미정'.
        project: 프로젝트 번호. 비우면 내 현재 프로젝트가 하나일 때 그것 (여러 개면 물어봐요).
    """
    if not title.strip():
        raise ToolError("할 일 내용이 비어 있어요.")
    _check_member(assignee)
    if _parse_date(due) is None:
        raise ToolError(f"마감 '{due}' 는 날짜 형식이 아니에요. YYYY-MM-DD 로 주세요 (예: 2026-11-20).")
    start = start or today().isoformat()
    if _parse_date(start) is None or start > due:
        raise ToolError(f"시작 '{start}' 는 YYYY-MM-DD 이고 마감({due}) 보다 늦으면 안 돼요.")
    if estimate_hours < 0:
        raise ToolError("예상 공수는 0 이상으로 주세요.")
    project = _resolve_project(project, assignee)
    rows = _read("tasks")
    task = {"번호": _next_id(rows), "할 일": title.strip(), "직군": role, "담당자": assignee, "상태": "할 일",
            "시작": start, "마감": due, "기준 마감": due, "예상 시간": str(estimate_hours or ""), "프로젝트": project}
    _write("tasks", rows + [task])
    return {"결과": f"할 일 #{task['번호']} 를 추가했어요.", "할 일": task, "노션 반영": _notion_hint(task)}


def update_task(
    task_id: str, editor: str, title: str = "", role: str = "", assignee: str = "",
    start: str = "", due: str = "", estimate_hours: float = -1, project: str = "",
) -> dict[str, Any]:
    """PO 가 할 일의 이름 · 직군 · 담당 · 기간 · 예상 공수를 고쳐요 (노션 '할 일 관리' 와 맞출 때도 써요).
    비운 칸은 그대로예요. 처음 마감(기준 마감)은 바꾸지 않아서 일정표에 '기간 변경됨' 으로 보여요. 상태는 update_task_status 로.

    Args:
        task_id: 할 일 번호.
        editor: 고치는 PO 아이디.
        title: 새 이름.
        role: 새 직군.
        assignee: 새 담당자 아이디.
        start: 새 시작 YYYY-MM-DD.
        due: 새 마감 YYYY-MM-DD.
        estimate_hours: 새 예상 공수 (음수면 그대로).
        project: 새 프로젝트 번호.
    """
    _check_member(editor, "편집자")
    _check_self(editor, "편집자")
    if not _is_po(editor):
        raise ToolError(f"'{editor}' 는 PO 가 아니라서 할 일을 고칠 수 없어요. 상태 변경은 update_task_status, 기간은 request_extension 으로 요청해 주세요.")
    rows = _read("tasks")
    task = _find(rows, task_id, "할 일")
    before = dict(task)
    if title.strip():
        task["할 일"] = title.strip()
    if role.strip():
        task["직군"] = role.strip()
    if assignee:
        _check_member(assignee)
        task["담당자"] = assignee
    if project:
        task["프로젝트"] = _find_project(project.lstrip("#"))["번호"]
    for key, value in (("시작", start), ("마감", due)):
        if value:
            if _parse_date(value) is None:
                raise ToolError(f"{key} '{value}' 는 YYYY-MM-DD 로 주세요.")
            task[key] = value
    if task.get("시작") and task["시작"] > task["마감"]:
        raise ToolError(f"시작({task['시작']}) 이 마감({task['마감']}) 보다 늦을 수 없어요.")
    if estimate_hours >= 0:
        task["예상 시간"] = str(estimate_hours).rstrip("0").rstrip(".") if "." in str(estimate_hours) else str(estimate_hours)
    task["기준 마감"] = before.get("기준 마감") or before["마감"]
    changed = {k: f"{before.get(k, '')} → {task.get(k, '')}" for k in ("할 일", "직군", "담당자", "시작", "마감", "예상 시간") if before.get(k, "") != task.get(k, "")}
    if not changed:
        return {"결과": f"할 일 #{task['번호']} 는 바뀐 게 없어요.", "바뀐 것": {}, "할 일": task}
    _write("tasks", rows)
    return {"결과": f"할 일 #{task['번호']} 를 고쳤어요.", "바뀐 것": changed, "할 일": task, "노션 반영": _notion_hint(task)}


def update_task_status(task_id: str, status: str) -> dict[str, Any]:
    """할 일의 상태를 바꿔요 (할 일 → 진행 중 → 완료). 지우는 대신 '완료' 로 바꿔요.

    Args:
        task_id: 할 일 번호.
        status: 할 일 / 진행 중 / 완료.
    """
    _check_choice(status, TASK_STATUSES, "상태")
    rows = _read("tasks")
    task = _find(rows, task_id, "할 일")
    before = task["상태"]
    task["상태"] = status
    _write("tasks", rows)
    return {"결과": f"할 일 #{task['번호']} 상태: {before} → {status}", "할 일": task, "노션 반영": _notion_hint(task)}


def log_work(
    member_id: str, summary: str, hours: float, task_id: str = "", work_date: str = "", link: str = ""
) -> dict[str, Any]:
    """팀원이 한 일을 작업 기록에 남겨요. 스탠드업 · 하루 마무리 때 쓰세요. 다른 사람 기록은 본인 요청 없이 쓰지 마세요.

    Args:
        member_id: 일한 사람 아이디.
        summary: 한 일 (한두 문장).
        hours: 걸린 시간 (0보다 크고 24 이하, 예: 1.5).
        task_id: 관련 할 일 번호 (있으면).
        work_date: 작업 날짜 YYYY-MM-DD (비우면 오늘).
        link: 한 일을 바로 볼 수 있는 주소 (PR · 커밋 · 노션 · 피그마 등, https:// 로 시작).
    """
    _check_member(member_id, "팀원")
    _check_self(member_id, "팀원")
    if not summary.strip():
        raise ToolError("한 일 내용이 비어 있어요.")
    if not 0 < hours <= 24:
        raise ToolError("시간은 0보다 크고 24 이하로 주세요.")
    if task_id:
        _find(_read("tasks"), task_id, "할 일")
    d = work_date or today().isoformat()
    if _parse_date(d) is None:
        raise ToolError(f"날짜 '{d}' 는 형식이 아니에요. YYYY-MM-DD 로 주세요.")
    rows = _read("worklog")
    if link and not link.startswith("https://"):
        raise ToolError("링크는 https:// 로 시작하는 주소로 주세요.")
    entry = {"번호": _next_id(rows), "날짜": d, "담당자": member_id, "할 일 번호": task_id.lstrip("#"),
             "내용": summary.strip(), "시간": str(hours), "링크": link.strip()}
    _write("worklog", rows + [entry])
    return {"결과": f"{member_id} 의 작업 기록 #{entry['번호']} 를 남겼어요.", "기록": entry}


# ── 회의 ──────────────────────────────────────────────────
def _hhmm(v: str) -> bool:
    parts = v.split(":")
    return len(parts) == 2 and all(x.isdigit() for x in parts) and 0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60 and len(v) == 5


def log_meeting(
    title: str, attendees: str, recorder: str, start: str, end: str,
    meeting_date: str = "", decisions: str = "", link: str = "",
) -> dict[str, Any]:
    """회의를 기록해요 (언제 · 누가 모였고 · 무엇을 정했는지 · 회의록 링크). 오피스 화면에서 참석자들이 회의실에 모였다가 흩어져요.
    노션 회의록을 읽고 기록할 때도 써요. 부르기 전에 내용을 사용자에게 보여 주고 승인받으세요.

    Args:
        title: 회의 제목 (예: 데일리 스탠드업).
        attendees: 참석자 아이디들, 쉼표나 띄어쓰기로 구분 (예: "po-seoan, dev-jaemin"). '전원' 이면 팀원 모두.
        recorder: 기록하는 사람 아이디 (본인).
        start: 시작 시각 HH:MM (예: 14:00).
        end: 끝 시각 HH:MM (시작보다 늦게).
        meeting_date: 날짜 YYYY-MM-DD (비우면 오늘).
        decisions: 결정 사항 (한두 줄).
        link: 회의록 주소 (노션 등, https:// 로 시작).
    """
    _check_member(recorder, "기록자")
    _check_self(recorder, "기록자")
    if not title.strip():
        raise ToolError("회의 제목이 비어 있어요.")
    ids = sorted({m["아이디"] for m in _read("members")}) if attendees.strip() == "전원" else [
        a for a in attendees.replace(",", " ").split() if a]
    if not ids:
        raise ToolError("참석자를 한 명 이상 적어 주세요 (아이디, 쉼표로 구분 · '전원' 가능).")
    for a in ids:
        _check_member(a, "참석자")
    if not (_hhmm(start) and _hhmm(end)) or end <= start:
        raise ToolError(f"시각은 HH:MM 이고 끝({end}) 이 시작({start}) 보다 늦어야 해요.")
    d = meeting_date or today().isoformat()
    if _parse_date(d) is None:
        raise ToolError(f"날짜 '{d}' 는 YYYY-MM-DD 로 주세요.")
    if link and not link.startswith("https://"):
        raise ToolError("회의록 링크는 https:// 로 시작하는 주소로 주세요.")
    rows = _read("meetings")
    if link.strip():
        dup = next((m for m in rows if m["링크"] == link.strip()), None)
        if dup:
            raise ToolError(f"이 회의록({link.strip()}) 은 이미 회의 #{dup['번호']} 로 기록돼 있어요. 다시 옮기지 않아도 돼요.")
    row = {"번호": _next_id(rows), "날짜": d, "시작": start, "끝": end, "제목": title.strip(), "참석자": " ".join(ids),
           "결정": decisions.strip(), "링크": link.strip(), "기록자": recorder}
    _write("meetings", rows + [row])
    return {"결과": f"회의 #{row['번호']} '{row['제목']}' ({d} {start}~{end}, {len(ids)}명) 을 기록했어요.", "회의": row}


def list_meetings(days: int = 7, member_id: str = "") -> dict[str, Any]:
    """최근 회의를 보여 줘요: 날짜 · 시간 · 제목 · 참석자 · 결정 사항 · 회의록 링크. '오늘 회의 뭐 있었어?', '내가 들어간 회의' 등에 쓰세요.

    Args:
        days: 최근 며칠 (기본 7일).
        member_id: 이 사람이 참석한 회의만 (비우면 전체).
    """
    since = today() - timedelta(days=days)
    rows = [
        {**m, "참석자": m["참석자"].split()} for m in _read("meetings")
        if (d := _parse_date(m["날짜"])) and d >= since and (not member_id or member_id in m["참석자"].split())
    ]
    rows.sort(key=lambda m: (m["날짜"], m["시작"]), reverse=True)
    return {"기간": f"{since.isoformat()} ~ {today().isoformat()}", "개수": len(rows), "회의": rows}


# ── 일정 · 공수 · 기간 변경 ──────────────────────────────────
EXT_STATUSES = ["대기", "승인", "반려"]


def _hours_by_task() -> dict[str, float]:
    out: dict[str, float] = {}
    for w in _read("worklog"):
        if w.get("할 일 번호"):
            out[w["할 일 번호"]] = round(out.get(w["할 일 번호"], 0) + float(w["시간"] or 0), 1)
    return out


def _float(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def schedule_overview(role: str = "", project: str = "") -> dict[str, Any]:
    """전체 업무 일정과 공수를 한눈에 보여 줘요: 할 일마다 시작 · 마감 · 기준 마감 · 예상 공수 · 실제 투입 시간,
    마감 지남(지연) · 공수 초과 · 기간 연장 여부, 관련 열린 이슈, 그리고 오늘 기준 계획 대비 진행률.
    '일정 어때?', '지연된 거 있어?', '공수 넘은 거', '오늘까지 얼마나 됐어?' 같은 질문에 쓰세요.

    Args:
        role: 직군으로 거르기 (비우면 전체).
        project: 프로젝트 번호로 거르기 (비우면 전체).
    """
    now = today()
    spent = _hours_by_task()
    issues = [i for i in _read("issues") if i["상태"] in ISSUE_OPEN]
    pending = {e["할 일 번호"] for e in _read("extensions") if e["상태"] == "대기"}
    rows, plan_total, plan_by_today, done_est, spent_total = [], 0.0, 0.0, 0.0, 0.0
    for t in _read("tasks"):
        if (role and t["직군"] != role) or not _in_project(t, project):
            continue
        start, due = _parse_date(t.get("시작", "")), _parse_date(t.get("마감", ""))
        base = _parse_date(t.get("기준 마감", "")) or due
        est, used = _float(t.get("예상 시간", "")), spent.get(t["번호"], 0.0)
        # 계획상 오늘까지 지나간 비율 (시작~마감 중 오늘까지 며칠 지났나)
        if start and due:
            total_days = (due - start).days + 1
            frac = min(1.0, max(0.0, ((now - start).days + 1) / total_days))
        else:
            frac = 0.0
        plan_total += est
        plan_by_today += est * frac
        spent_total += used
        if t["상태"] == "완료":
            done_est += est
        late = bool(due and now > due and t["상태"] != "완료")
        rows.append({
            **{k: t.get(k, "") for k in ("번호", "할 일", "직군", "담당자", "상태", "시작", "마감", "기준 마감", "프로젝트")},
            "예상 시간": est, "실제 시간": used,
            "공수 사용률": f"{round(used / est * 100)}%" if est else "미정",
            "계획 경과": f"{round(frac * 100)}%",
            "지연": late, "지연 일수": (now - due).days if late else 0,
            "공수 초과": bool(est and used > est),
            "연장됨": bool(base and due and due > base), "기간 변경됨": bool(base and due and due != base),
            "연장 대기": t["번호"] in pending,
            "열린 이슈": [i["번호"] for i in issues if i.get("관련 할 일") == t["번호"]],
        })
    pct = lambda v: round(v / plan_total * 100) if plan_total else 0  # noqa: E731
    return {
        "기준일": now.isoformat(),
        "요약": {
            "할 일 수": len(rows),
            "예상 공수 합계": round(plan_total, 1),
            "실제 투입 시간": round(spent_total, 1),
            "오늘까지 계획 진행률": f"{pct(plan_by_today)}%",
            "완료 기준 진행률": f"{pct(done_est)}%",
            "투입 비율": f"{pct(spent_total)}%",
            "지연": [r["번호"] for r in rows if r["지연"]],
            "공수 초과": [r["번호"] for r in rows if r["공수 초과"]],
            "연장 대기": [r["번호"] for r in rows if r["연장 대기"]],
        },
        "설명": "오늘까지 계획 = 각 할 일의 예상 공수 × 시작~마감 중 오늘까지 지난 비율. 완료 기준 = 완료된 할 일의 예상 공수 ÷ 전체.",
        "할 일": rows,
    }


def list_extensions(status: str = "") -> dict[str, Any]:
    """기간 연장 신청 목록을 보여 줘요 (기본: 전부, 대기 먼저).

    Args:
        status: 대기 / 승인 / 반려 중 하나로 거르기.
    """
    rows = [e for e in _read("extensions") if not status or e["상태"] == status]
    rows.sort(key=lambda e: (e["상태"] != "대기", e["신청일"]), reverse=False)
    return {"개수": len(rows), "신청": rows}


def change_kind(old_start: str, old_due: str, new_start: str, new_due: str) -> str:
    """기간 변경 종류: 연장 · 단축 · 일정 이동 · 시작일 변경."""
    if new_due > old_due:
        return f"연장 +{(date.fromisoformat(new_due) - date.fromisoformat(old_due)).days}일"
    if new_due < old_due:
        return f"단축 -{(date.fromisoformat(old_due) - date.fromisoformat(new_due)).days}일"
    return "시작일 변경" if new_start != old_start else "변경 없음"


def request_extension(task_id: str, new_due: str, reason: str, requester: str, new_start: str = "") -> dict[str, Any]:
    """할 일의 기간을 바꾸고 싶을 때 PO 에게 기간 변경(연장 · 단축 · 일정 이동)을 신청해요.
    신청만 하고, 시작 · 마감은 PO 가 승인해야 바뀌어요. 부르기 전에 내용을 사용자에게 보여 주고 승인받으세요.

    Args:
        task_id: 할 일 번호.
        new_due: 바라는 새 마감 YYYY-MM-DD (늦추면 연장, 당기면 단축).
        reason: 왜 바꿔야 하는지 (한두 문장).
        requester: 신청하는 사람 아이디.
        new_start: 바라는 새 시작 YYYY-MM-DD (비우면 그대로). 시작과 마감을 같이 옮기면 일정 이동이에요.
    """
    _check_member(requester, "신청자")
    _check_self(requester, "신청자")
    task = _find(_read("tasks"), task_id, "할 일")
    if task["상태"] == "완료":
        raise ToolError(f"할 일 #{task['번호']} 는 이미 완료라 기간을 바꿀 수 없어요.")
    old_start = task.get("시작", "") or task["마감"]
    new_start = new_start or old_start
    if _parse_date(new_due) is None or _parse_date(new_start) is None:
        raise ToolError("날짜는 YYYY-MM-DD 로 주세요 (예: 2026-11-20).")
    if new_start > new_due:
        raise ToolError(f"시작({new_start}) 이 마감({new_due}) 보다 늦을 수 없어요.")
    if new_start == old_start and new_due == task["마감"]:
        raise ToolError(f"지금 기간({old_start} ~ {task['마감']}) 과 같아서 바뀐 게 없어요.")
    if not reason.strip():
        raise ToolError("변경 사유를 적어 주세요.")
    rows = _read("extensions")
    if any(e["할 일 번호"] == task["번호"] and e["상태"] == "대기" for e in rows):
        raise ToolError(f"할 일 #{task['번호']} 는 이미 대기 중인 기간 변경 신청이 있어요.")
    req = {"번호": _next_id(rows), "할 일 번호": task["번호"], "신청자": requester,
           "기존 시작": old_start, "요청 시작": new_start, "기존 마감": task["마감"], "요청 마감": new_due,
           "사유": reason.strip(), "상태": "대기", "검토자": "", "검토 메모": "", "신청일": today().isoformat(), "검토일": ""}
    _write("extensions", rows + [req])
    kind = change_kind(old_start, task["마감"], new_start, new_due)
    return {"결과": f"기간 변경 신청 #{req['번호']} ({kind}) 를 올렸어요. PO 가 승인하면 일정이 바뀌어요.", "종류": kind, "신청": req}


def review_extension(request_id: str, decision: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """PO 가 기간 변경(연장 · 단축 · 이동) 신청을 승인하거나 반려해요. 승인하면 할 일의 시작 · 마감이 요청대로 바뀌고,
    처음 마감은 '기준 마감' 에 남아요. PO 직군만 쓸 수 있어요. 부르기 전에 사용자 승인을 받으세요.

    Args:
        request_id: 기간 변경 신청 번호.
        decision: 승인 / 반려.
        reviewer: 검토하는 PO 아이디.
        note: 검토 메모 (반려면 이유를 적어 주세요).
    """
    if decision not in ("승인", "반려"):
        raise ToolError("decision 은 '승인' 또는 '반려' 예요.")
    _check_member(reviewer, "검토자")
    _check_self(reviewer, "검토자")
    if next(m for m in _read("members") if m["아이디"] == reviewer)["직군"] != "PO":
        raise ToolError(f"'{reviewer}' 는 PO 가 아니라서 기간 변경을 승인 · 반려할 수 없어요.")
    rows = _read("extensions")
    req = _find(rows, request_id, "기간 변경 신청")
    if req["상태"] != "대기":
        raise ToolError(f"기간 변경 신청 #{req['번호']} 는 이미 '{req['상태']}' 상태예요.")
    req.update({"상태": decision, "검토자": reviewer, "검토 메모": note.strip(), "검토일": today().isoformat()})
    changed = None
    if decision == "승인":
        tasks = _read("tasks")
        task = _find(tasks, req["할 일 번호"], "할 일")
        task["기준 마감"] = task.get("기준 마감") or task["마감"]
        new_start = req.get("요청 시작") or task.get("시작", "")
        changed = f"{task.get('시작', '')} ~ {task['마감']} → {new_start} ~ {req['요청 마감']}"
        task["시작"], task["마감"] = new_start, req["요청 마감"]
        _write("tasks", tasks)
    _write("extensions", rows)
    out = {"결과": f"기간 변경 신청 #{req['번호']} 를 {decision}했어요." + (f" 기간 {changed}" if changed else ""), "신청": req}
    if decision == "승인":
        out["노션 반영"] = _notion_hint(_find(_read("tasks"), req["할 일 번호"], "할 일"))
    return out


# ── 재택 근무: 출퇴근 · 휴가 · 실시간 상태 · 체크인 · 근무 시간 · 리마인더 ──
WORK_PLACES = ["재택", "사무실", "외부"]
PRESENCE_STATES = ["응답 가능", "집중", "회의 중", "자리 비움"]
LEAVE_KINDS = ["연차", "반차(오전)", "반차(오후)", "병가", "경조사", "외근"]
LEAVE_AWAY = {"연차", "병가", "경조사"}          # 하루 종일 쉬는 종류 → 그날 상태가 '근무' 가 아니에요
LEAVE_STATUSES = ["대기", "승인", "반려"]


def _work_rules() -> dict[str, Any]:
    """근무 규칙. settings.csv 에 '코어 타임'(11:00~16:00) · '퇴근 기준' · '점심 시간' · '기록 비율 기준' 이 있으면 그 값을 써요."""
    st = settings()
    core = st.get("코어 타임", "11:00~16:00").replace(" ", "").split("~")
    core = core if len(core) == 2 and all(_hhmm(c) for c in core) else ["11:00", "16:00"]
    off = st.get("퇴근 기준", "19:00")
    return {
        "코어 시작": core[0], "코어 끝": core[1],
        "퇴근 기준": off if _hhmm(off) else "19:00",
        "점심 시간": _float(st.get("점심 시간", "1")),            # 6시간 넘게 일하면 빼는 시간
        "기록 비율 기준": _float(st.get("기록 비율 기준", "50")),  # 근무 시간 중 작업 기록이 이 % 아래면 '기록 누락'
    }


def _minutes(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def _work_hours(start: str, end: str, lunch: float) -> float:
    """출근~퇴근 시간 (6시간 넘으면 점심 시간을 빼요)."""
    if not (start and end and _hhmm(start) and _hhmm(end)) or end <= start:
        return 0.0
    hours = (_minutes(end) - _minutes(start)) / 60
    if hours > 6:
        hours -= lunch
    return round(max(hours, 0), 1)


def _day_arg(day: str) -> str:
    d = day or today().isoformat()
    if _parse_date(d) is None:
        raise ToolError(f"날짜 '{d}' 는 YYYY-MM-DD 로 주세요.")
    return d


def _approved_leave(member_id: str, day: str, leaves: list[dict[str, str]] | None = None) -> dict[str, str] | None:
    for lv in leaves if leaves is not None else _read("leaves"):
        if lv["신청자"] == member_id and lv["상태"] == "승인" and lv["시작"] <= day <= (lv["끝"] or lv["시작"]):
            return lv
    return None


def _day_state(member: dict[str, str], day: str, leaves: list[dict[str, str]] | None = None) -> tuple[str, str]:
    """(그날 상태, 그날 일정). 상태: members.csv 의 상태가 '근무' 가 아니면 그대로, 승인된 종일 휴가면 그 종류, 아니면 '근무'.
    일정: 반차 · 외근처럼 근무는 하지만 알아 둘 것."""
    if member["상태"] != "근무":
        return member["상태"], ""
    lv = _approved_leave(member["아이디"], day, leaves)
    if lv and lv["종류"] in LEAVE_AWAY:
        return lv["종류"], ""
    return "근무", (lv["종류"] if lv else "")


def _presence_of(member_id: str, day: str) -> dict[str, str]:
    """그날 바꾼 실시간 상태만 (지난 날 상태는 비워요)."""
    row = next((p for p in _read("presence") if p["아이디"] == member_id), None)
    if not row or not row["바뀐 시각"].startswith(day):
        return {"상태": "", "메모": "", "바뀐 시각": ""}
    return {k: row[k] for k in ("상태", "메모", "바뀐 시각")}


def check_in(member_id: str, location: str = "재택", at: str = "", note: str = "", work_date: str = "") -> dict[str, Any]:
    """출근을 기록해요 (재택 · 사무실 · 외부). 하루에 한 번, 본인만. 부르기 전에 내용을 보여 주고 승인받으세요.

    Args:
        member_id: 출근하는 사람 아이디 (본인).
        location: 재택 / 사무실 / 외부 (기본 재택).
        at: 출근 시각 HH:MM (비우면 지금).
        note: 메모 (예: 병원 들렀다 늦게 시작).
        work_date: 날짜 YYYY-MM-DD (비우면 오늘, 앞날은 안 돼요). 깜빡한 날을 고칠 때만 쓰세요.
    """
    _check_member(member_id, "팀원")
    _check_self(member_id, "팀원")
    _check_choice(location, WORK_PLACES, "근무지")
    day = _day_arg(work_date)
    if day > today().isoformat():
        raise ToolError("앞날의 출근은 미리 기록할 수 없어요.")
    at = at or now_hhmm()
    if not _hhmm(at):
        raise ToolError(f"시각 '{at}' 는 HH:MM 으로 주세요 (예: 09:30).")
    rows = _read("attendance")
    dup = next((r for r in rows if r["날짜"] == day and r["아이디"] == member_id), None)
    if dup:
        raise ToolError(f"{member_id} 는 {day} 에 이미 {dup['출근']} 출근으로 기록돼 있어요 (출근 #{dup['번호']}).")
    row = {"번호": _next_id(rows), "날짜": day, "아이디": member_id, "출근": at, "퇴근": "", "근무지": location, "메모": note.strip()}
    _write("attendance", rows + [row])
    out: dict[str, Any] = {"결과": f"{member_id} {day} {at} 출근 ({location}) 을 기록했어요.", "출근": row}
    member = next(m for m in _read("members") if m["아이디"] == member_id)
    state, plan = _day_state(member, day)
    if state != "근무":
        out["주의"] = f"{day} 는 '{state}' 로 잡혀 있어요. 휴가를 취소하려면 PO 에게 말해 주세요."
    if plan:
        out["오늘 일정"] = plan
    rules = _work_rules()
    if at > rules["코어 시작"] and plan != "반차(오전)":
        out["코어 타임"] = f"코어 타임({rules['코어 시작']}~{rules['코어 끝']}) 시작보다 늦었어요."
    return out


def check_out(member_id: str, at: str = "", note: str = "", work_date: str = "") -> dict[str, Any]:
    """퇴근을 기록해요. 그날 출근 기록이 있어야 해요. 본인만. 부르기 전에 내용을 보여 주고 승인받으세요.

    Args:
        member_id: 퇴근하는 사람 아이디 (본인).
        at: 퇴근 시각 HH:MM (비우면 지금, 출근보다 늦어야 해요).
        note: 메모 (기존 메모 뒤에 붙어요).
        work_date: 날짜 YYYY-MM-DD (비우면 오늘).
    """
    _check_member(member_id, "팀원")
    _check_self(member_id, "팀원")
    day = _day_arg(work_date)
    at = at or now_hhmm()
    if not _hhmm(at):
        raise ToolError(f"시각 '{at}' 는 HH:MM 으로 주세요 (예: 18:30).")
    rows = _read("attendance")
    row = next((r for r in rows if r["날짜"] == day and r["아이디"] == member_id), None)
    if not row:
        raise ToolError(f"{member_id} 의 {day} 출근 기록이 없어요. 먼저 check_in 으로 출근을 남겨 주세요.")
    if row["퇴근"]:
        raise ToolError(f"{day} 는 이미 {row['퇴근']} 퇴근으로 기록돼 있어요.")
    if at <= row["출근"]:
        raise ToolError(f"퇴근({at}) 이 출근({row['출근']}) 보다 늦어야 해요.")
    row["퇴근"] = at
    if note.strip():
        row["메모"] = f"{row['메모']} / {note.strip()}" if row["메모"] else note.strip()
    _write("attendance", rows)
    rules = _work_rules()
    hours = _work_hours(row["출근"], at, rules["점심 시간"])
    logged = round(sum(_float(w["시간"]) for w in _read("worklog") if w["담당자"] == member_id and w["날짜"] == day), 1)
    out: dict[str, Any] = {"결과": f"{member_id} {day} {row['출근']}~{at} 퇴근을 기록했어요. 근무 {hours}시간 · 작업 기록 {logged}시간.",
                           "출근": row, "근무 시간": hours, "작업 기록 시간": logged}
    if hours and logged / hours * 100 < rules["기록 비율 기준"]:
        out["기록 누락"] = f"작업 기록이 근무 시간의 {round(logged / hours * 100)}% 예요. 빠진 일이 있으면 log_work 로 남겨 주세요."
    return out


def set_status(member_id: str, status: str, note: str = "") -> dict[str, Any]:
    """지금 상태(응답 가능 · 집중 · 회의 중 · 자리 비움)와 한 줄 메모를 바꿔요. 동료가 '지금 말 걸어도 되나' 를 알 수 있어요.
    본인만 바꿀 수 있어요. 상태는 그날만 보여요 (다음 날엔 비어요).

    Args:
        member_id: 본인 아이디.
        status: 응답 가능 / 집중 / 회의 중 / 자리 비움.
        note: 한 줄 메모 (예: 15시까지 집중, 급하면 DM).
    """
    _check_member(member_id, "팀원")
    _check_self(member_id, "팀원")
    _check_choice(status, PRESENCE_STATES, "상태")
    rows = _read("presence")
    stamp = f"{today().isoformat()} {now_hhmm()}"
    before = _presence_of(member_id, today().isoformat())["상태"]
    row = next((p for p in rows if p["아이디"] == member_id), None)
    if row:
        row.update({"상태": status, "메모": note.strip(), "바뀐 시각": stamp})
    else:
        row = {"아이디": member_id, "상태": status, "메모": note.strip(), "바뀐 시각": stamp}
        rows.append(row)
    _write("presence", rows)
    out: dict[str, Any] = {"결과": f"{member_id} 상태: {before or '없음'} → {status}" + (f" ({note.strip()})" if note.strip() else ""), "상태": row}
    if not any(a["날짜"] == today().isoformat() and a["아이디"] == member_id for a in _read("attendance")):
        out["안내"] = "오늘 출근 기록이 아직 없어요. check_in 으로 남기면 근무 현황에 함께 보여요."
    return out


def attendance(day: str = "", member_id: str = "") -> dict[str, Any]:
    """하루 근무 현황을 보여 줘요: 누가 출근 · 퇴근했는지, 근무지, 근무 시간, 지금 상태(집중 · 회의 중 …), 휴가,
    데일리 체크인 제출 여부, 코어 타임을 지켰는지, 작업 기록이 근무 시간에 비해 얼마나 되는지.
    '지금 누가 일해?', '오늘 출근 현황', '○○ 지금 말 걸어도 돼?' 같은 질문에 쓰세요.

    Args:
        day: 날짜 YYYY-MM-DD (비우면 오늘).
        member_id: 한 사람만 보기 (비우면 전체).
    """
    d = _day_arg(day)
    is_today = d == today().isoformat()
    now = now_hhmm()
    rules = _work_rules()
    leaves = _read("leaves")
    att = {a["아이디"]: a for a in _read("attendance") if a["날짜"] == d}
    checks = {c["아이디"]: c for c in _read("checkins") if c["날짜"] == d}
    logs: dict[str, float] = {}
    for w in _read("worklog"):
        if w["날짜"] == d:
            logs[w["담당자"]] = round(logs.get(w["담당자"], 0) + _float(w["시간"]), 1)
    rows = []
    for m in _read("members"):
        mid = m["아이디"]
        if member_id and mid != member_id:
            continue
        state, plan = _day_state(m, d, leaves)
        a = att.get(mid, {})
        start, end = a.get("출근", ""), a.get("퇴근", "")
        working = bool(start and not end and is_today)
        hours = _work_hours(start, end or (now if working and now > start else ""), rules["점심 시간"])
        logged = logs.get(mid, 0.0)
        core = ""
        if start:
            late = start > rules["코어 시작"] and plan != "반차(오전)"
            early = bool(end) and end < rules["코어 끝"] and plan != "반차(오후)"
            core = "늦게 시작" if late else "일찍 끝" if early else "지킴"
        pres = _presence_of(mid, d) if (working or not is_today) else {"상태": "", "메모": "", "바뀐 시각": ""}
        rows.append({
            "아이디": mid, "이름": m["이름"], "직군": m["직군"], "상태": state, "일정": plan,
            "출근": start, "퇴근": end, "근무지": a.get("근무지", ""), "메모": a.get("메모", ""),
            "근무 중": working, "근무 시간": hours, "작업 기록 시간": logged,
            "기록 비율": f"{round(logged / hours * 100)}%" if hours else "",
            "실시간 상태": pres["상태"], "상태 메모": pres["메모"], "상태 바뀐 시각": pres["바뀐 시각"][11:],
            "체크인": mid in checks, "막힘": checks.get(mid, {}).get("막힘", ""), "코어 타임": core,
        })
    on_duty = [r for r in rows if r["상태"] == "근무"]
    return {
        "날짜": d, "지금": now if is_today else "", "규칙": rules,
        "요약": {
            "근무 예정": len(on_duty),
            "출근": sum(1 for r in on_duty if r["출근"]),
            "근무 중": sum(1 for r in rows if r["근무 중"]),
            "퇴근": sum(1 for r in rows if r["퇴근"]),
            "휴가 · 부재": [f"{r['이름']}({r['상태']})" for r in rows if r["상태"] != "근무"],
            "출근 기록 없음": [r["아이디"] for r in on_duty if not r["출근"]],
            "체크인 제출": sum(1 for r in rows if r["체크인"]),
            "코어 타임 벗어남": [r["아이디"] for r in rows if r["코어 타임"] in ("늦게 시작", "일찍 끝")],
            "근무 시간 합계": round(sum(r["근무 시간"] for r in rows), 1),
        },
        "팀원": rows,
    }


def work_hours(member_id: str = "", days: int = 7) -> dict[str, Any]:
    """최근 N일 동안 사람마다 근무 시간(출근~퇴근)과 작업 기록 시간을 비교해요. 근무는 했는데 작업 기록이 적은 날('기록 누락')을 찾아요.
    감시용이 아니라 기록 빠뜨린 날을 챙기는 용도예요. '이번 주 근무 시간', '기록 빠진 날 있어?' 에 쓰세요.

    Args:
        member_id: 한 사람만 (비우면 전체).
        days: 최근 며칠 (기본 7일, 오늘 포함).
    """
    if days < 1:
        raise ToolError("days 는 1 이상으로 주세요.")
    rules = _work_rules()
    since = today() - timedelta(days=days - 1)
    span = [(since + timedelta(days=i)).isoformat() for i in range(days)]
    att = [a for a in _read("attendance") if a["날짜"] in span]
    logs = [w for w in _read("worklog") if w["날짜"] in span]
    now, now_day = now_hhmm(), today().isoformat()
    people = []
    for m in _read("members"):
        mid = m["아이디"]
        if member_id and mid != member_id:
            continue
        daily = []
        for d in span:
            a = next((x for x in att if x["아이디"] == mid and x["날짜"] == d), None)
            logged = round(sum(_float(w["시간"]) for w in logs if w["담당자"] == mid and w["날짜"] == d), 1)
            if not a and not logged:
                continue
            start = a["출근"] if a else ""
            end = (a["퇴근"] if a else "") or (now if a and d == now_day and now > start else "")
            hours = _work_hours(start, end, rules["점심 시간"])
            finished = bool(a and a["퇴근"])
            ratio = round(logged / hours * 100) if hours else None
            daily.append({
                "날짜": d, "출근": start, "퇴근": a["퇴근"] if a else "", "근무 시간": hours,
                "작업 기록 시간": logged, "기록 비율": f"{ratio}%" if ratio is not None else "",
                "기록 누락": bool(finished and ratio is not None and ratio < rules["기록 비율 기준"]),
                "퇴근 기록 없음": bool(a and not a["퇴근"] and d < now_day),
            })
        total_h = round(sum(x["근무 시간"] for x in daily), 1)
        total_l = round(sum(x["작업 기록 시간"] for x in daily), 1)
        people.append({
            "아이디": mid, "이름": m["이름"], "직군": m["직군"], "출근일": sum(1 for x in daily if x["출근"]),
            "근무 시간": total_h, "작업 기록 시간": total_l,
            "기록 비율": f"{round(total_l / total_h * 100)}%" if total_h else "",
            "기록 누락일": [x["날짜"] for x in daily if x["기록 누락"]],
            "퇴근 기록 없음": [x["날짜"] for x in daily if x["퇴근 기록 없음"]],
            "날짜별": daily,
        })
    return {"기간": f"{span[0]} ~ {span[-1]}", "규칙": rules,
            "설명": f"근무 시간 = 퇴근 - 출근 (6시간 넘으면 점심 {rules['점심 시간']:g}시간 빼기, 오늘은 지금까지). "
                    f"기록 누락 = 퇴근한 날 작업 기록이 근무 시간의 {rules['기록 비율 기준']:g}% 아래.",
            "팀원": people}


def list_leaves(status: str = "", member_id: str = "", from_date: str = "") -> dict[str, Any]:
    """휴가 · 부재(연차 · 반차 · 병가 · 경조사 · 외근) 신청 목록을 보여 줘요 (대기 먼저, 그다음 가까운 날짜 순).
    사유는 본인과 PO 에게만 보여요.

    Args:
        status: 대기 / 승인 / 반려 로 거르기.
        member_id: 신청자 아이디로 거르기.
        from_date: 이 날짜 이후에 끝나는 것만 YYYY-MM-DD (예: 앞으로의 일정만 보려면 오늘 날짜).
    """
    mine = me()
    see_all = not mine or _is_po(mine)
    rows = [
        {**lv, "사유": lv["사유"] if see_all or lv["신청자"] == mine else "(본인 · PO 만 보여요)"}
        for lv in _read("leaves")
        if (not status or lv["상태"] == status) and (not member_id or lv["신청자"] == member_id)
        and (not from_date or (lv["끝"] or lv["시작"]) >= from_date)
    ]
    rows.sort(key=lambda lv: (lv["상태"] != "대기", lv["시작"]))
    return {"개수": len(rows), "신청": rows}


def request_leave(member_id: str, kind: str, start: str, end: str = "", reason: str = "") -> dict[str, Any]:
    """휴가 · 부재를 PO 에게 신청해요 (연차 · 반차(오전) · 반차(오후) · 병가 · 경조사 · 외근). PO 가 승인하면 그날 근무 현황에 반영돼요.
    본인만 신청할 수 있어요. 부르기 전에 내용을 사용자에게 보여 주고 승인받으세요.

    Args:
        member_id: 신청하는 사람 아이디 (본인).
        kind: 연차 / 반차(오전) / 반차(오후) / 병가 / 경조사 / 외근.
        start: 시작일 YYYY-MM-DD.
        end: 마지막 날 YYYY-MM-DD (비우면 하루). 반차는 하루만.
        reason: 사유 (선택, 본인과 PO 만 봐요).
    """
    _check_member(member_id, "신청자")
    _check_self(member_id, "신청자")
    _check_choice(kind, LEAVE_KINDS, "종류")
    end = end or start
    if _parse_date(start) is None or _parse_date(end) is None:
        raise ToolError("날짜는 YYYY-MM-DD 로 주세요 (예: 2026-11-20).")
    if start > end:
        raise ToolError(f"시작({start}) 이 끝({end}) 보다 늦을 수 없어요.")
    if kind.startswith("반차") and start != end:
        raise ToolError("반차는 하루만 신청할 수 있어요.")
    rows = _read("leaves")
    clash = next((lv for lv in rows if lv["신청자"] == member_id and lv["상태"] in ("대기", "승인")
                  and lv["시작"] <= end and start <= (lv["끝"] or lv["시작"])), None)
    if clash:
        raise ToolError(f"{clash['시작']} ~ {clash['끝']} 에 이미 '{clash['상태']}' 인 {clash['종류']} 신청(#{clash['번호']}) 이 있어요.")
    req = {"번호": _next_id(rows), "신청자": member_id, "종류": kind, "시작": start, "끝": end, "사유": reason.strip(),
           "상태": "대기", "검토자": "", "검토 메모": "", "신청일": today().isoformat(), "검토일": ""}
    _write("leaves", rows + [req])
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    span = start if days == 1 else f"{start} ~ {end} ({days}일)"
    return {"결과": f"{kind} 신청 #{req['번호']} ({span}) 를 올렸어요. PO 가 승인하면 근무 현황에 반영돼요.", "신청": req}


def review_leave(request_id: str, decision: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """PO 가 휴가 · 부재 신청을 승인하거나 반려해요. 승인하면 그 기간 근무 현황 · 오피스 화면에 휴가로 보여요.
    PO 직군만 쓸 수 있어요. 부르기 전에 사용자 승인을 받으세요.

    Args:
        request_id: 휴가 신청 번호.
        decision: 승인 / 반려.
        reviewer: 검토하는 PO 아이디 (본인).
        note: 검토 메모 (반려면 이유를 꼭 적어 주세요).
    """
    if decision not in ("승인", "반려"):
        raise ToolError("decision 은 '승인' 또는 '반려' 예요.")
    _check_member(reviewer, "검토자")
    _check_self(reviewer, "검토자")
    if not _is_po(reviewer):
        raise ToolError(f"'{reviewer}' 는 PO 가 아니라서 휴가를 승인 · 반려할 수 없어요. PO 에게 요청해 주세요.")
    rows = _read("leaves")
    req = _find(rows, request_id, "휴가 신청")
    if req["상태"] != "대기":
        raise ToolError(f"휴가 신청 #{req['번호']} 는 이미 '{req['상태']}' 상태예요.")
    if decision == "반려" and not note.strip():
        raise ToolError("반려할 때는 이유를 note 에 적어 주세요.")
    req.update({"상태": decision, "검토자": reviewer, "검토 메모": note.strip(), "검토일": today().isoformat()})
    _write("leaves", rows)
    return {"결과": f"휴가 신청 #{req['번호']} ({req['신청자']} · {req['종류']} · {req['시작']}~{req['끝']}) 를 {decision}했어요.", "신청": req}


def submit_checkin(member_id: str, yesterday: str, today_plan: str, blockers: str = "") -> dict[str, Any]:
    """데일리 체크인(어제 한 일 · 오늘 할 일 · 막힌 것)을 남겨요. 하루에 한 번, 본인만. 스탠드업 초안을 만든 뒤 저장할 때 쓰세요.
    부르기 전에 내용을 사용자에게 보여 주고 승인받으세요.

    Args:
        member_id: 본인 아이디.
        yesterday: 어제 한 일 (한두 문장).
        today_plan: 오늘 할 일 (한두 문장).
        blockers: 막힌 것 · 도움이 필요한 것 (없으면 비우기).
    """
    _check_member(member_id, "팀원")
    _check_self(member_id, "팀원")
    if not today_plan.strip():
        raise ToolError("오늘 할 일이 비어 있어요.")
    rows = _read("checkins")
    d = today().isoformat()
    if any(c["날짜"] == d and c["아이디"] == member_id for c in rows):
        raise ToolError(f"{member_id} 는 오늘({d}) 체크인을 이미 남겼어요.")
    row = {"번호": _next_id(rows), "날짜": d, "아이디": member_id, "어제": yesterday.strip(), "오늘": today_plan.strip(), "막힘": blockers.strip()}
    _write("checkins", rows + [row])
    out: dict[str, Any] = {"결과": f"{member_id} 의 {d} 체크인 #{row['번호']} 를 남겼어요.", "체크인": row}
    if row["막힘"]:
        out["안내"] = "막힌 것이 있어요. 오래 걸릴 것 같으면 create_issue 로 이슈를 등록하면 PO 에게 '담당 지정 필요' 로 보여요."
    return out


def list_checkins(day: str = "") -> dict[str, Any]:
    """하루의 데일리 체크인을 보여 줘요: 누가 무엇을 하는지, 막힌 사람, 아직 안 낸 사람(휴가 빼고).
    '오늘 체크인 어때?', '막힌 사람 있어?' 에 쓰세요.

    Args:
        day: 날짜 YYYY-MM-DD (비우면 오늘).
    """
    d = _day_arg(day)
    leaves = _read("leaves")
    names = {m["아이디"]: m["이름"] for m in _read("members")}
    rows = [{**c, "이름": names.get(c["아이디"], "")} for c in _read("checkins") if c["날짜"] == d]
    done = {c["아이디"] for c in rows}
    missing = [m["아이디"] for m in _read("members") if m["아이디"] not in done and _day_state(m, d, leaves)[0] == "근무"]
    return {"날짜": d, "제출": len(rows), "미제출": missing, "막힘": [c for c in rows if c["막힘"]], "체크인": rows}


def reminders(day: str = "") -> dict[str, Any]:
    """지금 챙겨야 할 알림 목록과 슬랙에 보낼 메시지 초안을 만들어요: 출근 기록 없음 · 체크인 미제출 · 퇴근 기록 없음 ·
    작업 기록 없음 · 막힌 사람 · 내일까지 마감 · PO 승인 대기(휴가 · 기간 변경).
    이 도구는 보내지 않아요. 슬랙으로 보내기 전에 초안을 사용자에게 보여 주고 승인받으세요.

    Args:
        day: 날짜 YYYY-MM-DD (비우면 오늘).
    """
    d = _day_arg(day)
    rules = _work_rules()
    is_today = d == today().isoformat()
    now = now_hhmm() if is_today else "23:59"
    view = attendance(d)
    names = {r["아이디"]: r["이름"] for r in view["팀원"]}
    duty = [r for r in view["팀원"] if r["상태"] == "근무"]
    out: dict[str, Any] = {
        "기준": f"{d} {now}" if is_today else d,
        "출근 기록 없음": [r["아이디"] for r in duty if not r["출근"] and now >= rules["코어 시작"]
                       and not (r["일정"] == "반차(오전)" and now < "14:00")],
        "체크인 미제출": [r["아이디"] for r in duty if r["출근"] and not r["체크인"]],
        "퇴근 기록 없음": [r["아이디"] for r in duty if r["출근"] and not r["퇴근"] and now >= rules["퇴근 기준"]],
        "작업 기록 없음": [r["아이디"] for r in duty if r["출근"] and not r["작업 기록 시간"]
                       and (r["퇴근"] or now >= rules["코어 끝"])],
        "막힘": [{"아이디": r["아이디"], "막힘": r["막힘"]} for r in view["팀원"] if r["막힘"]],
        "내일까지 마감": [{k: t[k] for k in ("번호", "할 일", "담당자", "마감")} for t in due_soon(1)["1일 안 마감"]] if is_today else [],
        "PO 승인 대기": {
            "휴가": [{k: lv[k] for k in ("번호", "신청자", "종류", "시작", "끝")} for lv in _read("leaves") if lv["상태"] == "대기"],
            "기간 변경": [{k: e[k] for k in ("번호", "할 일 번호", "신청자", "요청 마감")} for e in _read("extensions") if e["상태"] == "대기"],
        },
    }

    def who(ids: list[str]) -> str:
        return ", ".join(names.get(i, i) for i in ids)

    lines = [f"[재택 근무 알림] {out['기준']}"]
    for key, text in (("출근 기록 없음", "출근 체크가 아직 없어요"), ("체크인 미제출", "오늘 체크인을 남겨 주세요"),
                      ("퇴근 기록 없음", "퇴근 체크를 잊지 마세요"), ("작업 기록 없음", "오늘 작업 기록이 없어요")):
        if out[key]:
            lines.append(f"• {text}: {who(out[key])}")
    for b in out["막힘"]:
        lines.append(f"• 도움 필요 — {names.get(b['아이디'], b['아이디'])}: {b['막힘']}")
    for t in out["내일까지 마감"]:
        lines.append(f"• 마감 임박 — #{t['번호']} {t['할 일']} ({names.get(t['담당자'], t['담당자'] or '담당 없음')}, {t['마감']})")
    pend = out["PO 승인 대기"]
    if pend["휴가"] or pend["기간 변경"]:
        lines.append(f"• PO 승인 대기 — 휴가 {len(pend['휴가'])}건 · 기간 변경 {len(pend['기간 변경'])}건")
    out["알림 수"] = len(lines) - 1
    out["슬랙 메시지 초안"] = "\n".join(lines) if len(lines) > 1 else ""
    return out


# ── 직군별 MCP 세트 ──────────────────────────────────────────
def _roles() -> list[dict[str, str]]:
    """data/roles.csv — 직군마다 쓰는 team 도구와 외부 MCP."""
    path = data_dir() / "roles.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


def _catalog() -> dict[str, dict[str, str]]:
    path = data_dir() / "mcp_catalog.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["이름"]: {k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)}


REMOTE_TOOLS_ALL = ["attendance", "work_hours", "list_checkins", "list_leaves", "reminders",
                    "check_in", "check_out", "set_status", "submit_checkin", "request_leave"]
REMOTE_TOOLS_PO = ["review_leave"]
PROJECT_TOOLS_ALL = ["list_projects"]
PROJECT_TOOLS_PO = ["create_project", "update_project", "assign_member", "end_assignment",
                    "add_member", "list_access", "grant_access", "revoke_access"]


def tools_for_role(role: str) -> list[str]:
    """직군 이름(개발) 또는 키(dev)로 그 직군이 쓰는 team 도구 이름 목록을 돌려줘요.
    roles.csv 의 도구 + 재택 근무 · 프로젝트 보기(모든 직군) + 휴가 승인 · 프로젝트 관리(PO 만)."""
    for r in _roles():
        if role in (r["직군"], r["키"]):
            extra = REMOTE_TOOLS_ALL + PROJECT_TOOLS_ALL + (REMOTE_TOOLS_PO + PROJECT_TOOLS_PO if r["직군"] == "PO" else [])
            base = r["team 도구"].split()
            return base + [t for t in extra if t not in base]
    names = ", ".join(f"{r['직군']}({r['키']})" for r in _roles())
    raise ToolError(f"직군 '{role}' 는 roles.csv 에 없어요. 가능한 값: {names}")


def whoami() -> dict[str, Any]:
    """이 MCP 를 쓰고 있는 '나' 가 누구인지 알려 줘요: 팀원 아이디 · 이름 · 직군 · 쓸 수 있는 도구 · 붙이는 외부 MCP.
    사용자가 '나', '내 할 일', '내 이름으로' 라고 하면 먼저 이걸 부르세요.
    """
    mine = me()
    if not mine:
        return {"나": None, "안내": "TEAM_ME 가 설정되지 않았어요. setup_member.py <내 아이디> 로 연결하면 '나' 를 알아봐요.",
                "팀원 아이디": [f"{m['아이디']} ({m['이름']} · {m['직군']})" for m in _read("members")]}
    member = next((m for m in _read("members") if m["아이디"] == mine), None)
    if not member:
        raise ToolError(f"TEAM_ME='{mine}' 가 members.csv 에 없어요. 팀원 아이디를 확인해 주세요.")
    kit = role_toolkit(member["직군"])["직군별"]
    return {
        "나": member,
        "직군 MCP": kit[0] if kit else None,
        "이 서버에 켜진 도구": sorted(t.name for t in mcp._tool_manager.list_tools()),
        "규칙": "작업 기록 · 이슈 등록 · 기간 변경 요청은 내 이름으로만 할 수 있어요." + (" 나는 PO 라서 승인 · 담당 지정도 할 수 있어요." if member["직군"] == "PO" else ""),
    }


def role_toolkit(role: str = "") -> dict[str, Any]:
    """직군(직무)별로 쓰는 MCP 세트를 보여 줘요: team 도구 중 무엇을 쓰는지 + 외부 MCP(깃허브 · 피그마 등) 무엇을 붙이는지.
    '개발자는 어떤 MCP 써?', '직무별 MCP', '내 직군 도구' 같은 질문에 쓰세요.

    Args:
        role: 직군 이름(개발 · 디자인 · PO · 마케팅) 또는 키(dev · design · po · mkt). 비우면 전체.
    """
    catalog = _catalog()
    out = []
    for r in _roles():
        if role and role not in (r["직군"], r["키"]):
            continue
        out.append({
            "직군": r["직군"], "키": r["키"], "설명": r["설명"],
            "팀원": [m["이름"] for m in _read("members") if m["직군"] == r["직군"]],
            "team 도구": tools_for_role(r["직군"]),
            "외부 MCP": [catalog.get(n, {"이름": n, "주소": "", "연결": "목록에 없음", "용도": ""}) for n in r["외부 MCP"].split()],
        })
    if role and not out:
        tools_for_role(role)  # 없는 직군이면 안내 메시지와 함께 에러
    return {"이 서버의 직군": os.environ.get("TEAM_ROLE", "") or "전체", "직군별": out}


# ── 프로젝트 · 배치 (쓰기는 PO 만) ───────────────────────────
def _check_po(requester: str, action: str) -> None:
    """본인 이름으로만 + PO 만."""
    _check_member(requester, "요청자")
    _check_self(requester, "요청자")
    if not _is_po(requester):
        raise ToolError(f"{action} 는 PO 만 할 수 있어요. PO 에게 요청해 주세요.")


def _check_date(value: str, label: str) -> str:
    if _parse_date(value) is None:
        raise ToolError(f"{label} '{value}' 는 날짜 형식이 아니에요. YYYY-MM-DD 로 주세요 (예: 2026-11-20).")
    return value


def _find_project(project_id: str) -> dict[str, str]:
    rows = _read("projects")
    for p in rows:
        if p["번호"] == str(project_id).strip():
            return p
    ids = ", ".join(p["번호"] for p in rows) or "없음"
    raise ToolError(f"프로젝트 '{project_id}' 는 없어요. 가능한 번호: {ids} (list_projects 로 보기)")


def _active(row: dict[str, str], day: str) -> bool:
    return row["시작"] <= day and (not row["종료"] or day <= row["종료"])


def current_projects(member_id: str, day: str = "") -> list[str]:
    """그날(기본 오늘) 현재 참여 중인 프로젝트 번호들 — 배치 기간 안이고 프로젝트가 '진행' 이에요."""
    day = day or today().isoformat()
    running = {p["번호"] for p in _read("projects") if p["상태"] == "진행"}
    ids = {a["프로젝트"] for a in _read("project_members")
           if a["아이디"] == member_id and a["프로젝트"] in running and _active(a, day)}
    return sorted(ids, key=lambda x: (len(x), x))


def list_projects(status: str = "") -> dict[str, Any]:
    """프로젝트 목록과 현재 참여자 · 배치 이력 · 담당 관리자를 보여 줘요. '프로젝트 누가 해?', '배치 현황' 에 쓰세요.

    Args:
        status: 진행 / 종료 중 하나. 비우면 전체.
    """
    if status:
        _check_choice(status, PROJECT_STATUSES, "프로젝트 상태")
    day = today().isoformat()
    assigned = _read("project_members")
    out = []
    for p in _read("projects"):
        if status and p["상태"] != status:
            continue
        rows = [a for a in assigned if a["프로젝트"] == p["번호"]]
        now = sorted({a["아이디"] for a in rows if p["상태"] == "진행" and _active(a, day)})
        out.append({**p, "현재 참여": now, "배치": rows})
    return {"개수": len(out), "프로젝트": out}


def create_project(name: str, start: str, end: str, manager: str, requester: str,
                   include_existing: bool = False) -> dict[str, Any]:
    """새 프로젝트를 만들어요 (PO 만). 부르기 전에 사용자 승인을 받으세요.

    Args:
        name: 프로젝트 이름.
        start: 시작일 YYYY-MM-DD.
        end: 종료일 YYYY-MM-DD (비우면 정하지 않음).
        manager: 담당 관리자 아이디.
        requester: 요청자 = 나 (PO).
        include_existing: 처음 한 번만 — 지금 팀원 전원을 배치하고, 프로젝트가 빈 할 일 · 이슈를 이 프로젝트로 넣어요.
    """
    _check_po(requester, "프로젝트 만들기")
    if not name.strip():
        raise ToolError("프로젝트 이름이 비어 있어요.")
    _check_date(start, "시작")
    if end:
        _check_date(end, "종료")
        if end < start:
            raise ToolError(f"종료({end}) 가 시작({start}) 보다 빨라요.")
    _check_member(manager, "담당 관리자")
    rows = _read("projects")
    if include_existing and rows:
        raise ToolError("include_existing 은 프로젝트가 하나도 없을 때(처음) 한 번만 쓸 수 있어요.")
    project = {"번호": _next_id(rows), "이름": name.strip(), "시작": start, "종료": end, "담당 관리자": manager,
               "상태": "진행", "만든 날": today().isoformat()}
    _write("projects", rows + [project])
    result: dict[str, Any] = {"결과": f"프로젝트 #{project['번호']} '{project['이름']}' 를 만들었어요.", "프로젝트": project}
    if include_existing:
        assigned = _read("project_members")
        for m in _read("members"):
            assigned.append({"번호": _next_id(assigned), "프로젝트": project["번호"], "아이디": m["아이디"],
                             "시작": start, "종료": "", "메모": "처음 옮길 때 전원 배치"})
        _write("project_members", assigned)
        moved = {}
        for table in ("tasks", "issues"):
            items = _read(table)
            n = 0
            for it in items:
                if not it.get("프로젝트"):
                    it["프로젝트"] = project["번호"]
                    n += 1
            _write(table, items)
            moved[table] = n
        result["옮김"] = {"배치": len(_read("members")), "할 일": moved["tasks"], "이슈": moved["issues"]}
    return result


def update_project(project_id: str, requester: str, name: str = "", start: str = "", end: str = "",
                   manager: str = "", status: str = "") -> dict[str, Any]:
    """프로젝트의 이름 · 기간 · 담당 관리자 · 상태(진행 · 종료)를 바꿔요 (PO 만). 빈 값은 그대로 둬요. 부르기 전에 승인을 받으세요."""
    _check_po(requester, "프로젝트 고치기")
    rows = _read("projects")
    p = _find_project(project_id)
    p = next(r for r in rows if r["번호"] == p["번호"])
    if status:
        _check_choice(status, PROJECT_STATUSES, "프로젝트 상태")
    if manager:
        _check_member(manager, "담당 관리자")
    new_start = _check_date(start, "시작") if start else p["시작"]
    new_end = _check_date(end, "종료") if end else p["종료"]
    if new_end and new_end < new_start:
        raise ToolError(f"종료({new_end}) 가 시작({new_start}) 보다 빨라요.")
    p.update({"이름": name.strip() or p["이름"], "시작": new_start, "종료": new_end,
              "담당 관리자": manager or p["담당 관리자"], "상태": status or p["상태"]})
    _write("projects", rows)
    return {"결과": f"프로젝트 #{p['번호']} 를 고쳤어요.", "프로젝트": p}


def assign_member(project_id: str, member_id: str, start: str, requester: str, end: str = "",
                  note: str = "") -> dict[str, Any]:
    """팀원을 프로젝트에 배치해요 (PO 만). 부르기 전에 사용자 승인을 받으세요.

    Args:
        project_id: 프로젝트 번호.
        member_id: 배치할 팀원 아이디.
        start: 참여 시작일 YYYY-MM-DD.
        requester: 요청자 = 나 (PO).
        end: 참여 종료일 (비우면 계속).
        note: 메모.
    """
    _check_po(requester, "프로젝트 배치")
    p = _find_project(project_id)
    _check_member(member_id, "팀원")
    _check_date(start, "시작")
    if end:
        _check_date(end, "종료")
        if end < start:
            raise ToolError(f"종료({end}) 가 시작({start}) 보다 빨라요.")
    rows = _read("project_members")
    for a in rows:
        if a["프로젝트"] == p["번호"] and a["아이디"] == member_id and \
                (not a["종료"] or a["종료"] >= start) and (not end or a["시작"] <= end):
            raise ToolError(f"{member_id} 는 이미 프로젝트 #{p['번호']} 에 배치돼 있어요 (배치 #{a['번호']}, "
                            f"{a['시작']} ~ {a['종료'] or '계속'}). 끝내려면 end_assignment 를 쓰세요.")
    row = {"번호": _next_id(rows), "프로젝트": p["번호"], "아이디": member_id, "시작": start, "종료": end, "메모": note.strip()}
    _write("project_members", rows + [row])
    return {"결과": f"{member_id} 를 프로젝트 #{p['번호']} '{p['이름']}' 에 배치했어요.", "배치": row}


def end_assignment(assignment_id: str, end: str, requester: str) -> dict[str, Any]:
    """배치를 끝내요 — 종료일만 적고 지우지 않아요 (PO 만). 부르기 전에 승인을 받으세요."""
    _check_po(requester, "배치 끝내기")
    _check_date(end, "종료")
    rows = _read("project_members")
    a = _find(rows, assignment_id, "배치")
    if end < a["시작"]:
        raise ToolError(f"종료({end}) 가 시작({a['시작']}) 보다 빨라요.")
    a["종료"] = end
    _write("project_members", rows)
    return {"결과": f"배치 #{a['번호']} ({a['아이디']} · 프로젝트 #{a['프로젝트']}) 를 {end} 에 끝냈어요.", "배치": a}


MEMBER_ID_RE = re.compile(r"^[a-z]+-[a-z0-9]+$")


def add_member(member_id: str, name: str, role: str, requester: str) -> dict[str, Any]:
    """새 팀원을 추가해요 (PO 만). 이메일 · 깃헙 아이디는 여기 넣지 않아요 (오피스 화면 관리자 전용). 부르기 전에 승인을 받으세요.

    Args:
        member_id: 새 아이디 — 직군 키-영문 이름 (예: dev-gangi). 소문자 · 숫자 · 하이픈 한 개.
        name: 이름.
        role: 직군 (roles.csv 에 있는 것).
        requester: 요청자 = 나 (PO).
    """
    _check_po(requester, "팀원 추가")
    member_id = member_id.strip()
    if not MEMBER_ID_RE.match(member_id):
        raise ToolError(f"아이디 모양이 맞지 않아요: '{member_id}'. 직군 키-영문 이름처럼 써 주세요 (예: dev-gangi).")
    if member_id in _member_ids():
        raise ToolError(f"아이디 '{member_id}' 는 이미 있어요. 다른 아이디를 써 주세요 (예: {member_id}2).")
    if not name.strip():
        raise ToolError("이름이 비어 있어요.")
    roles = [r["직군"] for r in _roles()]
    if role not in roles:
        raise ToolError(f"직군 '{role}' 는 roles.csv 에 없어요. 가능한 값: {', '.join(roles)}")
    rows = _read("members")
    member = {"아이디": member_id, "이름": name.strip(), "직군": role, "역할": "팀원", "상태": "근무"}
    _write("members", rows + [member])
    return {"결과": f"{member['이름']}({member_id}) 를 팀원으로 추가했어요. 키트를 다시 받으려면 레포에 푸시해야 해요.",
            "팀원": member}


def _valid_access() -> list[dict[str, str]]:
    return [g for g in _read("access") if g["상태"] == "유효"]


def list_access(requester: str, viewer: str = "") -> dict[str, Any]:
    """관리자가 더 열어 준 공개 범위(유효한 것)를 보여 줘요 (PO 만).

    Args:
        requester: 요청자 = 나 (PO).
        viewer: 보는 사람 아이디로 거르기 (비우면 전체).
    """
    _check_po(requester, "공개 범위 보기")
    rows = [g for g in _valid_access() if not viewer or g["보는 사람"] == viewer]
    return {"개수": len(rows), "범위": rows}


def grant_access(viewer: str, target: str, items: list[str], requester: str) -> dict[str, Any]:
    """보는 사람(viewer)에게 대상(target)의 항목을 더 보여 줘요 (PO 만). 부르기 전에 승인을 받으세요.

    Args:
        viewer: 보는 사람 아이디.
        target: 대상 아이디 또는 '전원'.
        items: '작업 기록' · '할 일' · '이슈' 중 하나 이상.
        requester: 요청자 = 나 (PO).
    """
    _check_po(requester, "공개 범위 열기")
    _check_member(viewer, "보는 사람")
    if target != "전원":
        _check_member(target, "대상")
    if not items:
        raise ToolError(f"항목을 하나 이상 골라 주세요: {', '.join(ACCESS_ITEMS)}")
    for it in items:
        if it not in ACCESS_ITEMS:
            raise ToolError(f"항목 '{it}' 는 고를 수 없어요. 가능한 값: {', '.join(ACCESS_ITEMS)} "
                            "(출퇴근 · 근무 시간은 원래 누구나 봐요).")
    rows = _read("access")
    valid = _valid_access()
    added, existing = [], []
    for it in dict.fromkeys(items):
        same = next((g for g in valid if g["보는 사람"] == viewer and g["대상"] == target and g["항목"] == it), None)
        if same:
            existing.append(same)
            continue
        row = {"번호": _next_id(rows), "보는 사람": viewer, "대상": target, "항목": it, "부여자": requester,
               "날짜": today().isoformat(), "상태": "유효"}
        rows.append(row)
        added.append(row)
    if added:
        _write("access", rows)
    return {"결과": f"{viewer} 가 {target} 의 {', '.join(g['항목'] for g in added) or '(새로 연 것 없음)'} 를 볼 수 있어요.",
            "추가": added, "이미 있음": existing}


def revoke_access(grant_id: str, requester: str) -> dict[str, Any]:
    """연 범위를 회수해요 — 지우지 않고 상태를 '회수' 로 바꿔요 (PO 만). 부르기 전에 승인을 받으세요."""
    _check_po(requester, "공개 범위 회수")
    rows = _read("access")
    g = _find(rows, grant_id, "공개 범위")
    g["상태"] = "회수"
    _write("access", rows)
    return {"결과": f"공개 범위 #{g['번호']} ({g['보는 사람']} → {g['대상']} · {g['항목']}) 를 회수했어요.", "범위": g}


ALL_TOOLS = [
    (team_dashboard, "팀 대시보드", READ),
    (list_members, "팀원 목록", READ),
    (member_status, "팀원 한 명 현황", READ),
    (list_tasks, "할 일 보기", READ),
    (progress, "진행률", READ),
    (list_issues, "이슈 목록", READ),
    (get_issue, "이슈 하나 보기", READ),
    (due_soon, "마감 임박", READ),
    (work_log, "작업 기록 보기", READ),
    (role_toolkit, "직무별 MCP 세트", READ),
    (whoami, "나는 누구 (TEAM_ME)", READ),
    (list_meetings, "회의 보기", READ),
    (schedule_overview, "전체 일정 · 공수", READ),
    (list_extensions, "기간 변경 신청 목록", READ),
    (request_extension, "기간 변경 · 연장 신청", WRITE),
    (review_extension, "기간 변경 승인 · 반려 (PO)", WRITE),
    (create_issue, "이슈 등록", WRITE),
    (update_issue, "이슈 상태 · 메모 바꾸기", WRITE),
    (assign_issue, "이슈 담당 지정 (PO)", WRITE),
    (add_task, "할 일 추가", WRITE),
    (update_task_status, "할 일 상태 바꾸기", WRITE),
    (update_task, "할 일 고치기 (PO)", WRITE),
    (log_work, "작업 기록 남기기", WRITE),
    (log_meeting, "회의 기록", WRITE),
]

# 재택 근무 도구 — roles.csv 와 따로 모든 직군에 켜요 (휴가 승인은 PO 만)
REMOTE_TOOLS = [
    (attendance, "오늘 근무 현황 (출퇴근 · 상태 · 휴가)", READ),
    (work_hours, "근무 시간 · 작업 기록 비교", READ),
    (list_checkins, "데일리 체크인 보기", READ),
    (list_leaves, "휴가 · 부재 신청 목록", READ),
    (reminders, "재택 근무 알림 · 슬랙 초안", READ),
    (check_in, "출근 기록", WRITE),
    (check_out, "퇴근 기록", WRITE),
    (set_status, "지금 상태 바꾸기", WRITE),
    (submit_checkin, "데일리 체크인 남기기", WRITE),
    (request_leave, "휴가 · 부재 신청", WRITE),
    (review_leave, "휴가 승인 · 반려 (PO)", WRITE),
]

# 프로젝트 · 배치 · 팀원 · 공개 범위 — 모든 직군에 켜요 (쓰기는 도구 안에서 PO 만)
PROJECT_TOOLS = [
    (list_projects, "프로젝트 · 배치 보기", READ),
    (create_project, "프로젝트 만들기 (PO)", WRITE),
    (update_project, "프로젝트 고치기 (PO)", WRITE),
    (assign_member, "프로젝트 배치 (PO)", WRITE),
    (end_assignment, "배치 끝내기 (PO)", WRITE),
    (add_member, "팀원 추가 (PO)", WRITE),
    (list_access, "공개 범위 보기 (PO)", READ),
    (grant_access, "공개 범위 열기 (PO)", WRITE),
    (revoke_access, "공개 범위 회수 (PO)", WRITE),
]

# 등록 규칙
#   TEAM_ROLE=개발   → roles.csv 의 '개발' 줄에 적힌 도구만 (직군마다 다른 MCP)
#   TEAM_READONLY=1  → 쓰기 도구는 빼기
_role = os.environ.get("TEAM_ROLE", "").strip()
if not _role and me():
    _role = next((m["직군"] for m in _read("members") if m["아이디"] == me()), "")
_allowed = set(tools_for_role(_role)) if _role else None
_readonly = os.environ.get("TEAM_READONLY", "") in ("1", "true", "yes")
for fn, title, ann in ALL_TOOLS + REMOTE_TOOLS + PROJECT_TOOLS:
    if _readonly and ann is WRITE:
        continue
    if _allowed is not None and fn.__name__ not in _allowed:
        continue
    mcp.add_tool(fn, title=title, annotations=ann)


# ── 리소스 · 프롬프트 ────────────────────────────────────────
@mcp.resource("team://members", title="팀원 명단", mime_type="text/csv")
def members_resource() -> str:
    """members.csv 원문 — 아이디 · 이름 · 직군 · 역할 · 상태."""
    path = data_dir() / "members.csv"
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


@mcp.prompt(title="스탠드업 초안")
def standup(member_id: str) -> str:
    """팀원 한 명의 스탠드업(어제 한 일 · 오늘 할 일 · 막힌 것) 초안을 만들게 하는 명령 틀."""
    return (
        f"team 의 member_status(member_id='{member_id}', days=1) 를 불러서 {member_id} 의 스탠드업을 써 줘.\n"
        "- 어제 한 일: 작업 기록에서\n- 오늘 할 일: '진행 중' 할 일 먼저, 마감 가까운 순\n"
        "- 막힌 것: 맡은 열린 이슈 (없으면 '없음')\n"
        "데이터에 없는 내용은 지어내지 말고, 각 줄은 한 문장으로.\n"
        f"보여 준 뒤 내가 '저장' 이라고 하면 submit_checkin(member_id='{member_id}', yesterday, today_plan, blockers) 로 오늘 체크인에 남겨 줘."
    )


@mcp.prompt(title="재택 근무 알림 보내기")
def remote_reminder() -> str:
    """reminders 로 오늘 챙길 것을 모아 슬랙 메시지 초안을 만들고, 승인받으면 보내게 하는 명령 틀 (PO 용)."""
    return (
        "team 의 reminders() 를 불러서 '슬랙 메시지 초안' 을 그대로 보여 줘. 알림이 0건이면 '보낼 것 없음' 이라고만 말해.\n"
        "내가 보낼 채널을 알려 주고 '보내' 라고 하면 그때 slack_send_message 로 보내. 채널 설명에 이런 글을 올리지 말라고 돼 있으면 보내지 말고 알려 줘.\n"
        "초안에 없는 사람 · 숫자는 더하지 마. 매일 자동으로 보내고 싶다고 하면 /schedule 로 평일 정해진 시각에 이 명령을 돌리는 방법을 알려 줘."
    )


def settings() -> dict[str, str]:
    """data/settings.csv — 팀 규칙에 쓰는 주소 (예: 노션 회의록 DB)."""
    path = data_dir() / "settings.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["항목"].strip(): (r["값"] or "").strip() for r in csv.DictReader(f) if r.get("항목")}


@mcp.prompt(title="노션 회의록 가져오기")
def import_meetings() -> str:
    """팀 규칙: 회의록 정본은 노션 '회의록' DB. 완료됐는데 아직 team 에 안 옮긴 회의를 찾아 log_meeting 으로 옮기는 명령 틀."""
    db = settings().get("회의록 노션 DB", "(data/settings.csv 에 '회의록 노션 DB' 주소를 넣어 주세요)")
    return (
        f"노션 회의록 DB({db}) 를 읽어서, 상태가 '완료' 이고 'team 기록' 이 비어 있는 회의를 찾아 줘.\n"
        "각 회의를 team 의 log_meeting 으로 옮길 거야. 옮기기 전에 표로 먼저 보여 줘: 제목 · 날짜 · 시작 · 끝 · 참석자 · 결정 · 링크.\n"
        "칸 맞추기 규칙:\n"
        "- 제목 = '회의', 날짜 · 시작 · 끝 = '날짜' 속성의 시작~끝 (HH:MM)\n"
        "- 참석자 · 기록자 = 선택지 '이름 · 아이디' 에서 · 뒤의 아이디만\n"
        "- 결정 = '결정', 링크 = 그 노션 페이지 주소 (자료 링크가 아니라 회의록 페이지)\n"
        "- recorder 는 whoami 의 나. 내가 기록자가 아니면 기록자 이름을 알려 주고 그 사람에게 맡기라고 말해 줘.\n"
        "내가 '옮겨' 라고 하면 log_meeting 으로 기록하고, 노션 페이지의 'team 기록' 에 '회의 #번호' 를 적어 줘.\n"
        "이미 기록된 링크라는 에러가 나면 건너뛰고 'team 기록' 만 채워. 데이터에 없는 사람이나 시간은 지어내지 마."
    )


@mcp.prompt(title="대시보드 · 노션 → CSV 맞추기")
def sync_dashboard() -> str:
    """오피스 화면에서 입력한 것(작업 기록 · 이슈 · 상태 · 기간 승인 · 담당 지정 · 팀원 추가 · 프로젝트 배치 · 공개 범위)과
    노션 '할 일 관리' 를 team CSV 로 옮기는 명령 틀 (PO 용)."""
    st = settings()
    return (
        f"팀 오피스 화면({st.get('오피스 화면', '(settings.csv 의 오피스 화면 주소)')}) 의 공유 데이터와 "
        f"노션 할 일 관리 DB({st.get('할 일 노션 DB', '(settings.csv 의 할 일 노션 DB 주소)')}) 를 읽어서 team CSV 와 다른 점을 표로 보여 줘.\n"
        "읽을 곳: 화면 데이터 events(작업 기록 worklog · task_status · issue_status · issue_new), taskEdits, assignments, decisions, sync/state.done 에 없는 것만.\n"
        "노션: 번호가 같은 할 일은 할 일 · 직군 · 담당(· 뒤 아이디) · 상태 · 기간 · 예상 공수가 CSV 와 다르면 바꿀 목록에, 번호가 빈 행은 새 할 일로.\n"
        "내가 '옮겨' 라고 하면 team 도구로 하나씩: log_work · update_task_status · update_issue · create_issue · add_task · assign_issue · review_extension.\n"
        "새 할 일은 add_task 뒤 노션 행의 '번호' 를 새 번호로 채우고, 옮긴 화면 항목 id 는 sync/state 의 done 에 더해 줘.\n"
        "관리자 대기열도 읽어 (synced 가 아닌 것만, 관리자가 쓴 것만 — by 가 accounts 에 연결된 PO 계정이 아니면 건너뛰고 알려 줘): "
        "pendingMembers → add_member (project 가 있으면 그 문서의 start 를 시작일로 assign_member 도), "
        "pendingProjects → op 별로 create_project · update_project · assign_member · end_assignment, "
        "pendingAccess → grant_access · revoke_access. 옮긴 문서에는 synced: true 를 적어 줘.\n"
        "본인 이름 · PO 규칙에 막히는 건 건너뛰고 누구에게 맡겨야 하는지 알려 줘.\n"
        "웹(Vercel) 로그인용 이메일: ArtifactData 로 오피스 화면의 invites 를 읽어 {아이디: email} 을 work-remotely/.secrets/emails.json 에 써 "
        "(git 에 안 올라가요 · 이메일을 대화에 늘어놓지 마).\n"
        "다 끝나면 export_office.py 로 화면(office.html) · 웹 껍데기(web/) · 사람별 데이터(web-api/) 를 새로 만들고 오피스 화면을 같은 주소로 다시 게시해 "
        "(오피스 화면 주소는 settings.csv). 그다음 data/ · web/ · web-api/ 를 비공개 데이터 저장소에 커밋하고, 명령을 먼저 보여 준 뒤 푸시하면 "
        "Vercel 웹 화면이 새로 배포돼.\n"
        "팀원 명단이 바뀌었으면 make_kit.py --dir <임시 폴더> 로 데이터 없는 키트를 만들어 공개 키트 저장소(ayla-seoan/work-remotely-kit)에 "
        "커밋하고, 먼저 보여 준 뒤 푸시해."
    )


@mcp.prompt(title="주간 보고 초안")
def weekly_report() -> str:
    """팀 주간 보고 초안을 만들게 하는 명령 틀."""
    return (
        "team 의 team_dashboard 와 work_log(days=7) 를 불러서 주간 보고를 써 줘.\n"
        "1) 진행률 (전체 · 직군별)  2) 이번 주 사람별 한 일 · 시간  3) 열린 이슈 (긴급 · 높음 먼저)\n"
        "4) 다음 주 마감  5) 리소스: 일이 몰린 사람 · 여유 있는 사람\n"
        "숫자는 도구 결과 그대로 쓰고, 추측은 '추측' 이라고 표시해."
    )


if __name__ == "__main__":
    mcp.run()  # 기본 stdio — Claude Code · 데스크톱이 이 프로세스의 입출력으로 대화해요.
