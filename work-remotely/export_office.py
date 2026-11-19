"""team MCP 의 실제 도구 결과를 모아 오피스 화면(office/office.html)을 만들어요.

    uv run python export_office.py            # 오늘 날짜 기준
    $env:TEAM_TODAY="2026-11-17"; uv run python export_office.py   # 샘플 데이터 기준
    uv run python export_office.py 미리보기.html   # 다른 파일로 (직군 설정 파일은 안 만들어요)
    uv run python export_office.py 미리보기.html --as dev-kangi   # 그 사람 눈에 보이는 화면만 (full · public 도 돼요)

화면에는 전체 · 공개 · 팀원별 스냅샷이 모두 들어가고, 화면이 보는 사람에 맞는 것을 골라 그려요
(화면에서만 가리기 — 설계 문서 §2). 사람별 스냅샷은 visibility.py 로 거른 데이터로 같은 도구를 다시 불러 만들어요.

화면은 브라우저에서 MCP 서버에 직접 붙을 수 없어서(stdio), 이 스크립트가 서버의 읽기 도구를
한 번씩 불러 그 결과를 HTML 안에 넣어요. 데이터가 바뀌면 다시 실행하면 돼요.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import team_server as s
from visibility import filter_tables, scope_for

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "office" / "template.html"
OUTPUT = HERE / "office" / "office.html"
WEB = HERE / "web" / "index.html"   # Vercel 정적 화면 — 데이터 없는 껍데기 (로그인 뒤 /api/data 로 받아요)
WEB_API = HERE / "web-api"           # Vercel 함수만 읽는 사람별 데이터 (정적으로는 안 나가요)
SECRETS = HERE / ".secrets" / "emails.json"  # {아이디: 이메일} — 새로 고침이 오피스 화면에서 읽어 와요 (git 에 안 올려요)
WEB_NOTE = "웹 공개 화면 · 읽기 전용이에요. 입력 · 팀원 추가 · 내 프로젝트만 보기는 claude.ai 오피스 화면에서 해요."


def snapshot() -> dict:
    members = s.list_members()["팀원"]
    tools = []
    for t in s.mcp._tool_manager.list_tools():
        tools.append({
            "name": t.name,
            "title": t.title or t.name,
            "readOnly": bool(t.annotations and t.annotations.read_only_hint),
            "summary": (t.description or "").strip().splitlines()[0],
        })
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": s.today().isoformat(),
        "server": {"name": s.mcp.name, "version": "0.2.0"},
        "tools": tools,
        # 아래는 모두 MCP 도구를 그대로 부른 결과예요.
        "team_dashboard": s.team_dashboard(),
        "list_members": s.list_members(),
        "progress": s.progress(),
        "list_issues": s.list_issues(status="전체"),
        "due_soon": s.due_soon(3),
        "work_log": s.work_log(days=30),
        "member_status": {m["아이디"]: s.member_status(m["아이디"], days=7) for m in members},
        "tasks": s.list_tasks()["할 일"],
        "role_toolkit": s.role_toolkit(),
        "schedule_overview": s.schedule_overview(),
        "list_meetings": s.list_meetings(days=14),
        "list_extensions": s.list_extensions(),
        "list_projects": s.list_projects(),
        "list_access": {"범위": [g for g in s._read("access") if g["상태"] == "유효"]},  # 사람별 보기에는 본인 줄만 남아요
        # 재택 근무
        "attendance": s.attendance(),
        "attendance_by_day": attendance_by_day(),
        "work_hours": s.work_hours(days=7),
        "list_checkins": s.list_checkins(),
        "list_leaves": public_leaves(),
        "reminders": s.reminders(),
        # 키트 보내기 (관리자 화면의 설치 안내 메일)
        "kit": {"zip": KIT_ZIP, "repo": REPO, "office": s.settings().get("오피스 화면", ""), "web": WEB_URL},
        "mcp_catalog": list(s._catalog().values()),
        "tool_sources": TOOL_SOURCES,
        "built_with": BUILT_WITH,
    }


VIEW_TABLES = ("members", "tasks", "issues", "worklog", "checkins", "meetings", "extensions", "projects",
               "project_members", "access", "attendance", "leaves")


def _log_open(scope: dict):
    """작업 기록(체크인 포함)이 보이는 사람인지 — 본인 · 같은 프로젝트 동료 · 관리자가 연 사람."""
    v = scope["member"]
    open_ = set(scope["coPeople"]) | ({v} if v else set())
    g = scope["grants"].get("작업 기록", [])
    return lambda person: bool(v) and (person in open_ or person in g or "전원" in g)


def _hide_logs(snap: dict, scope: dict) -> None:
    """볼 수 없는 사람의 작업 기록에서 나온 숫자 · 체크인은 0 · 미제출이 아니라 None(모름)으로 바꿔요.
    거른 데이터로 다시 계산하면 그 사람은 '기록 0 · 미제출' 로 보여 거짓 경고가 되니까요."""
    see = _log_open(scope)

    def att(a: dict) -> None:
        shown = 0
        for m in a.get("팀원", []):
            if see(m["아이디"]):
                shown += m.get("상태") == "근무"
                continue
            m.update({"체크인": None, "막힘": "", "작업 기록 시간": None, "기록 비율": None})
        if "요약" in a:
            a["요약"]["체크인 대상"] = shown

    att(snap["attendance"])
    for day in snap["attendance_by_day"].values():
        att(day)
    ck = snap.get("list_checkins") or {}
    if "미제출" in ck:
        ck["미제출"] = [i for i in ck["미제출"] if see(i)]
    for m in snap["work_hours"].get("팀원", []):
        if see(m["아이디"]):
            continue
        m.update({"작업 기록 시간": None, "기록 비율": None, "기록 누락일": None})
        for d in m.get("날짜별", []):
            d.update({"작업 기록 시간": None, "기록 비율": None, "기록 누락": None})
    for m in snap["list_members"]["팀원"] + snap["team_dashboard"].get("팀원별", []):
        if not see(m["아이디"]):
            m.update({"최근 7일 작업 시간": None, "마지막 작업일": None})
    for mid, st in snap["member_status"].items():
        if not see(mid):
            for k in list(st):
                if "작업 시간" in k:
                    st[k] = None


def _own_reminders(r: dict, viewer: str) -> dict:
    """알림은 본인 것만 (PO 승인 대기 · 슬랙 초안은 관리자 화면에서만)."""
    def mine(item) -> bool:
        if isinstance(item, dict):
            return bool(viewer) and viewer in (item.get("아이디"), item.get("담당자"), item.get("신청자"))
        return bool(viewer) and item == viewer
    out = {k: ([x for x in v if mine(x)] if isinstance(v, list) else v) for k, v in r.items()}
    out["PO 승인 대기"] = {"휴가": [], "기간 변경": []}  # 화면 모양은 그대로, 내용은 관리자만
    out["알림 수"] = sum(len(v) for v in out.values() if isinstance(v, list))
    out["슬랙 메시지 초안"] = ""
    return out


def snapshot_for(viewer: str) -> dict:
    """viewer 가 볼 수 있는 데이터만으로 만든 스냅샷 ('' = 공개). 진짜 data/ 는 건드리지 않아요."""
    src = s.data_dir()
    tables = {name: s._read(name) for name in VIEW_TABLES}
    scope = scope_for(viewer, tables, s.today().isoformat())
    filtered = filter_tables(scope, tables)
    old = os.environ.get("TEAM_DATA_DIR")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "data"
        if src.exists():
            shutil.copytree(src, folder)
        else:
            folder.mkdir()
        os.environ["TEAM_DATA_DIR"] = str(folder)
        try:
            for name, rows in filtered.items():
                if name in s.FIELDS and (rows or (folder / f"{name}.csv").exists()):
                    s._write(name, rows)
            snap = snapshot()
        finally:
            if old is None:
                os.environ.pop("TEAM_DATA_DIR", None)
            else:
                os.environ["TEAM_DATA_DIR"] = old
    _hide_logs(snap, scope)
    snap["reminders"] = _own_reminders(snap["reminders"], viewer)
    snap["scope"] = scope
    return snap


def build_payload(only: str = "", note: str = "") -> dict:
    """화면에 넣을 데이터. only 를 주면 미리보기용으로 그 보기 하나만 (아이디 · 'full' · 'public').
    note 는 화면 위 '누가 보는 중' 줄에 띄울 안내 (웹 판)."""
    if only:
        if only == "full":
            one = {**snapshot(), "scope": None}
        else:
            one = snapshot_for("" if only == "public" else only)
        return {"full": None, "public": None, "views": {}, "preview": one, "note": note}
    return {
        "full": {**snapshot(), "scope": None},
        "public": snapshot_for(""),
        "views": {m["아이디"]: snapshot_for(m["아이디"]) for m in s._read("members")},
        "preview": None,
    }


def attendance_by_day(days: int = 30) -> dict:
    """출퇴근 기록이 있는 날마다 그날 근무 현황 (오피스 하루 다시 보기에서 출근 · 퇴근 시각에 맞춰 움직여요)."""
    since = (s.today() - timedelta(days=days)).isoformat()
    dates = sorted({a["날짜"] for a in s._read("attendance") if since <= a["날짜"] <= s.today().isoformat()} | {s.today().isoformat()})
    return {d: s.attendance(d) for d in dates}


def public_leaves() -> dict:
    """화면은 팀 모두가 봐서 휴가 사유는 빼요 (사유는 list_leaves 로 본인 · PO 만)."""
    out = s.list_leaves(from_date=(s.today() - timedelta(days=14)).isoformat())
    out["신청"] = [{k: v for k, v in lv.items() if k != "사유"} for lv in out["신청"]]
    return out


# 팀원이 받는 키트 — 데이터 없는 공개 저장소의 main 압축 파일 (데이터 저장소는 비공개)
KIT_REPO = "https://github.com/ayla-seoan/work-remotely-kit"
REPO = KIT_REPO
KIT_ZIP = KIT_REPO + "/archive/refs/heads/main.zip"
WEB_URL = "https://work-remotely-kappa.vercel.app"   # Vercel 웹 화면 (구글 로그인)


# team 도구마다 읽고 쓰는 데이터 파일
TOOL_SOURCES = {
    "team_dashboard": ["tasks.csv", "issues.csv", "members.csv", "worklog.csv"],
    "list_members": ["members.csv", "tasks.csv", "issues.csv", "worklog.csv"],
    "member_status": ["members.csv", "tasks.csv", "issues.csv", "worklog.csv"],
    "list_tasks": ["tasks.csv"],
    "progress": ["tasks.csv"],
    "list_issues": ["issues.csv"],
    "get_issue": ["issues.csv", "tasks.csv"],
    "due_soon": ["tasks.csv"],
    "work_log": ["worklog.csv"],
    "role_toolkit": ["roles.csv", "mcp_catalog.csv", "members.csv"],
    "whoami": ["members.csv", "roles.csv"],
    "list_meetings": ["meetings.csv"],
    "log_meeting": ["meetings.csv ✎"],
    "create_issue": ["issues.csv ✎"],
    "update_issue": ["issues.csv ✎"],
    "assign_issue": ["issues.csv ✎"],
    "add_task": ["tasks.csv ✎"],
    "update_task_status": ["tasks.csv ✎"],
    "log_work": ["worklog.csv ✎"],
    "schedule_overview": ["tasks.csv", "worklog.csv", "issues.csv", "extensions.csv"],
    "list_extensions": ["extensions.csv"],
    "request_extension": ["extensions.csv ✎"],
    "review_extension": ["extensions.csv ✎", "tasks.csv ✎"],
    "attendance": ["attendance.csv", "leaves.csv", "presence.csv", "checkins.csv", "worklog.csv"],
    "work_hours": ["attendance.csv", "worklog.csv"],
    "list_checkins": ["checkins.csv", "leaves.csv"],
    "list_leaves": ["leaves.csv"],
    "reminders": ["attendance.csv", "checkins.csv", "leaves.csv", "tasks.csv", "extensions.csv"],
    "check_in": ["attendance.csv ✎"],
    "check_out": ["attendance.csv ✎"],
    "set_status": ["presence.csv ✎"],
    "submit_checkin": ["checkins.csv ✎"],
    "request_leave": ["leaves.csv ✎"],
    "review_leave": ["leaves.csv ✎"],
}

# team MCP 를 만든 도구 · 프로그램
BUILT_WITH = [
    {"이름": "MCP Python SDK 2.x", "용도": "서버 본체 (MCPServer · stdio)", "사이트": "https://github.com/modelcontextprotocol/python-sdk"},
    {"이름": "Model Context Protocol", "용도": "AI 앱과 도구를 잇는 표준", "사이트": "https://modelcontextprotocol.io"},
    {"이름": "uv", "용도": "파이썬 환경 · 실행", "사이트": "https://docs.astral.sh/uv/"},
    {"이름": "pytest", "용도": "자동 테스트", "사이트": "https://docs.pytest.org"},
    {"이름": "MCP Inspector", "용도": "화면에서 도구 눌러 보기", "사이트": "https://github.com/modelcontextprotocol/inspector"},
    {"이름": "Claude Code", "용도": "MCP 를 연결해 쓰는 AI 클라이언트", "사이트": "https://docs.claude.com/en/docs/claude-code/mcp"},
]


def role_configs() -> list[Path]:
    """직군마다 쓰는 MCP 만 담은 설정 파일 roles/<키>.mcp.json 을 만들어요.

    쓰는 법 (레포 맨 위에서):  claude --mcp-config work-remotely/roles/dev.mcp.json
    claude.ai 커넥터(구글 등)는 주소가 없어서 파일에 넣지 않아요 — claude.ai 에서 연결하면 같이 보여요.
    """
    folder = HERE / "roles"
    folder.mkdir(exist_ok=True)
    written = []
    for role in s.role_toolkit()["직군별"]:
        servers = {
            "team": {
                "command": "uv",
                "args": ["run", "--directory", "work-remotely", "python", "team_server.py"],
                "env": {"PYTHONUTF8": "1", "TEAM_ROLE": role["직군"]},
            }
        }
        for mcp in role["외부 MCP"]:
            if not mcp.get("주소"):
                continue
            entry = {"type": "http", "url": mcp["주소"]}
            if mcp["이름"] == "github":
                entry["headers"] = {"Authorization": "Bearer ${GITHUB_PAT}"}  # 토큰 값은 환경변수에만
            servers[mcp["이름"]] = entry
        path = folder / f"{role['키']}.mcp.json"
        path.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
        # 팀원마다: 같은 세트 + TEAM_ME (나 = 이 아이디)
        people = HERE / "members"
        people.mkdir(exist_ok=True)
        for m in s.list_members(role=role["직군"])["팀원"]:
            mine = json.loads(json.dumps(servers))
            mine["team"]["env"]["TEAM_ME"] = m["아이디"]
            mp = people / f"{m['아이디']}.mcp.json"
            mp.write_text(json.dumps({"mcpServers": mine}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written.append(mp)
    return written


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    lib_path = HERE / "office" / "lib.js"
    lib = lib_path.read_text(encoding="utf-8").replace("</", "<\\/") if lib_path.exists() else ""
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__SNAPSHOT__*/null", data).replace("/*__LIB__*/", lib)


def email_hash(email: str) -> str:
    """이메일 → sha256 (앞뒤 공백 빼고 소문자). api/_lib.js 의 emailHash 와 같은 값이에요."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def write_web(path: Path = WEB) -> Path:
    """Vercel 정적 화면 web/index.html — 데이터 없이, 화면이 로그인 뒤 /api/data 를 불러요."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html({"remote": "/api/data", "note": WEB_NOTE}), encoding="utf-8")
    return path


def write_web_api(folder: Path = WEB_API, emails: dict | None = None) -> list[Path]:
    """함수 전용 데이터: views/<아이디>.json · full.json · accounts.json(이메일 해시 → 아이디).
    emails 가 없으면 SECRETS 파일을 쓰고, 그것도 없으면 있던 accounts.json 을 그대로 둬요."""
    folder = Path(folder)
    (folder / "views").mkdir(parents=True, exist_ok=True)
    written = []

    def dump(path: Path, obj) -> None:
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written.append(path)

    ids = [m["아이디"] for m in s._read("members")]
    for mid in ids:
        dump(folder / "views" / f"{mid}.json", build_payload(only=mid, note=WEB_NOTE))
    dump(folder / "full.json", build_payload(only="full", note=WEB_NOTE))
    if emails is None and SECRETS.exists():
        emails = json.loads(SECRETS.read_text(encoding="utf-8"))
    if emails is not None:
        dump(folder / "accounts.json", {email_hash(e): mid for mid, e in emails.items() if mid in ids and e and "@" in e})
    return written


def main() -> None:
    args = sys.argv[1:]
    only = ""
    if "--as" in args:
        i = args.index("--as")
        only = args[i + 1] if i + 1 < len(args) else ""
        if not only:
            raise SystemExit("--as 뒤에 아이디 · full · public 중 하나를 적어 주세요.")
        if only not in ("full", "public") and only not in {m["아이디"] for m in s._read("members")}:
            raise SystemExit(f"--as '{only}' 는 팀원 아이디가 아니에요.")
        args = args[:i] + args[i + 2:]
    html = render_html(build_payload(only))
    out = Path(args[0]).resolve() if args else OUTPUT
    out.write_text(html, encoding="utf-8")
    print(f"만들었어요: {out}")
    if out != OUTPUT:
        return  # 미리보기는 화면만
    print(f"웹(Vercel) 화면: {write_web()} · 사람별 데이터 {len(write_web_api())}개")
    for path in role_configs():
        print(f"직군 MCP 설정: {path}")


if __name__ == "__main__":
    main()
