"""프로젝트 · 배치 · 팀원 추가 · 공개 범위 도구 (기준일 2026-11-17)."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import team_server as s


def _fresh(data):
    """프로젝트가 아직 없는 상태 (마이그레이션 전)."""
    (data / "projects.csv").unlink()
    (data / "project_members.csv").unlink()
    for name in ("tasks", "issues"):
        rows = s._read(name)
        for r in rows:
            r["프로젝트"] = ""
        s._write(name, rows)


# ── 프로젝트 · 배치 ─────────────────────────────────────────
def test_list_projects_current_members(data):
    p1 = next(p for p in s.list_projects()["프로젝트"] if p["번호"] == "1")
    assert p1["현재 참여"] == ["design-miyoung", "dev-jaemin", "dev-kangi", "dev-myeonggeun", "po-seoan"]
    assert len(p1["배치"]) == 5


def test_list_projects_status_filter(data):
    assert s.list_projects(status="종료")["개수"] == 0
    assert s.list_projects()["개수"] == 2


def test_assignment_end_today_still_current(data):
    assert s.current_projects("dev-myeonggeun") == ["1"]
    assert s.current_projects("dev-myeonggeun", "2026-11-18") == []
    assert s.current_projects("po-seoan") == ["1", "2"]


def test_create_project_po_only(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    with pytest.raises(ToolError, match="PO 만"):
        s.create_project("새 프로젝트", "2026-11-20", "", "po-seoan", requester="dev-kangi")


def test_create_project_requester_must_be_me(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    with pytest.raises(ToolError, match="다른 사람 이름"):
        s.create_project("새 프로젝트", "2026-11-20", "", "po-seoan", requester="po-seoan")


def test_create_project_appends(data):
    r = s.create_project("새 프로젝트", "2026-11-20", "2026-12-20", "po-seoan", requester="po-seoan")
    assert r["프로젝트"]["번호"] == "3"
    assert r["프로젝트"]["상태"] == "진행"
    assert r["프로젝트"]["만든 날"] == "2026-11-17"


def test_create_project_validates_dates(data):
    with pytest.raises(ToolError, match="종료"):
        s.create_project("거꾸로", "2026-11-20", "2026-11-10", "po-seoan", requester="po-seoan")
    with pytest.raises(ToolError, match="날짜"):
        s.create_project("이상한 날", "11/20", "", "po-seoan", requester="po-seoan")


def test_create_project_include_existing(data):
    _fresh(data)
    r = s.create_project("현재 프로젝트", "2026-11-13", "", "po-seoan", requester="po-seoan", include_existing=True)
    assert r["프로젝트"]["번호"] == "1"
    assigned = s._read("project_members")
    assert sorted(a["아이디"] for a in assigned) == sorted(m["아이디"] for m in s._read("members"))
    assert {a["시작"] for a in assigned} == {"2026-11-13"}
    assert {t["프로젝트"] for t in s._read("tasks")} == {"1"}
    assert {i["프로젝트"] for i in s._read("issues")} == {"1"}


def test_include_existing_only_when_no_projects(data):
    with pytest.raises(ToolError, match="처음"):
        s.create_project("또", "2026-11-13", "", "po-seoan", requester="po-seoan", include_existing=True)


def test_assign_member_rejects_overlap(data):
    with pytest.raises(ToolError, match="이미"):
        s.assign_member("1", "dev-kangi", "2026-11-17", requester="po-seoan")


def test_assign_member_appends(data):
    r = s.assign_member("2", "dev-kangi", "2026-11-17", requester="po-seoan", note="지원")
    assert r["배치"]["프로젝트"] == "2"
    assert s.current_projects("dev-kangi") == ["1", "2"]


def test_assign_member_unknown_project(data):
    with pytest.raises(ToolError, match="프로젝트 '9'"):
        s.assign_member("9", "dev-kangi", "2026-11-17", requester="po-seoan")


def test_end_assignment_sets_date(data):
    before = len(s._read("project_members"))
    r = s.end_assignment("1", "2026-11-17", requester="po-seoan")
    assert r["배치"]["종료"] == "2026-11-17"
    assert len(s._read("project_members")) == before
    with pytest.raises(ToolError, match="시작"):
        s.end_assignment("1", "2026-10-01", requester="po-seoan")


def test_update_project_validates_status(data):
    with pytest.raises(ToolError, match="상태"):
        s.update_project("1", requester="po-seoan", status="보류")
    r = s.update_project("1", requester="po-seoan", status="종료", name="앱 출시 1차")
    assert r["프로젝트"]["상태"] == "종료"
    assert r["프로젝트"]["이름"] == "앱 출시 1차"
    assert s.current_projects("dev-kangi") == []  # 끝난 프로젝트는 현재 참여가 아니에요


# ── 기존 도구의 project 인자 ────────────────────────────────
def test_list_tasks_project_filter(data):
    rows = s.list_tasks(project="2")["할 일"]
    assert {t["번호"] for t in rows} == {"4", "7", "8", "9"}


def test_list_issues_project_filter(data):
    assert {i["번호"] for i in s.list_issues(status="전체", project="1")["이슈"]} == {"1", "4", "5"}


def test_add_task_defaults_to_only_project(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    r = s.add_task("테스트 할 일", "개발", "dev-kangi", "2026-11-25")
    assert r["할 일"]["프로젝트"] == "1"


def test_add_task_requires_project_when_many(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "po-seoan")
    with pytest.raises(ToolError, match="프로젝트를 정해 주세요.*1.*2"):
        s.add_task("테스트 할 일", "PO", "po-seoan", "2026-11-25")
    r = s.add_task("테스트 할 일", "PO", "po-seoan", "2026-11-25", project="2")
    assert r["할 일"]["프로젝트"] == "2"


def test_add_task_unknown_project(data):
    with pytest.raises(ToolError, match="프로젝트 '9'"):
        s.add_task("테스트 할 일", "개발", "dev-kangi", "2026-11-25", project="9")


def test_create_issue_gets_project(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    r = s.create_issue("테스트", "내용", "보통", "dev-kangi")
    assert r["이슈"]["프로젝트"] == "1"


def test_no_projects_file_keeps_old_behavior(data, monkeypatch):
    _fresh(data)
    monkeypatch.setenv("TEAM_ME", "po-seoan")
    r = s.add_task("테스트 할 일", "PO", "po-seoan", "2026-11-25")
    assert r["할 일"]["프로젝트"] == ""
    assert s.list_tasks()["개수"] == 11


def test_progress_by_project(data):
    assert s.progress(project="2")["전체"] == s._ratio(1, 4)  # #9 완료 / #4 #7 #8 #9
    assert s.progress()["전체"] == s._ratio(2, 10)


def test_dashboard_and_schedule_by_project(data):
    d = s.team_dashboard(project="2")
    assert d["진행률"]["전체"] == s._ratio(1, 4)
    assert {i["번호"] for i in d["급한 이슈"]} <= {"2", "3"}
    rows = s.schedule_overview(project="1")["할 일"]
    assert {r["번호"] for r in rows} == {"1", "2", "3", "5", "6", "10"}
    assert {r["프로젝트"] for r in rows} == {"1"}


# ── 새로 고침 명령 틀 ────────────────────────────────────────
def test_sync_dashboard_covers_pending_queues():
    text = s.sync_dashboard()
    for word in ("pendingMembers", "pendingProjects", "pendingAccess", "add_member", "create_project",
                 "assign_member", "end_assignment", "grant_access", "revoke_access", "synced", "푸시",
                 "관리자가 쓴 것만", "start"):
        assert word in text, word


def test_sync_dashboard_covers_web_login():
    text = s.sync_dashboard()
    for word in ("invites", ".secrets/emails.json", "web-api", "work-remotely-kit", "Vercel", "make_kit.py --dir"):
        assert word in text, word


# ── 팀원 추가 · 공개 범위 ───────────────────────────────────
def test_add_member_validates(data):
    with pytest.raises(ToolError, match="아이디 모양"):
        s.add_member("Dev-X", "가나다", "개발", requester="po-seoan")
    with pytest.raises(ToolError, match="이미"):
        s.add_member("dev-kangi", "김강이", "개발", requester="po-seoan")
    with pytest.raises(ToolError, match="직군 '외계'.*개발"):
        s.add_member("dev-gangi", "김강이", "외계", requester="po-seoan")


def test_add_member_appends(data):
    r = s.add_member("dev-gangi", "김강이", "개발", requester="po-seoan")
    assert r["팀원"] == {"아이디": "dev-gangi", "이름": "김강이", "직군": "개발", "역할": "팀원", "상태": "근무"}
    assert s.list_members()["팀원 수"] == 8


def test_add_member_po_only(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    with pytest.raises(ToolError, match="PO 만"):
        s.add_member("dev-gangi", "김강이", "개발", requester="dev-kangi")


def test_grant_access_dedupes(data):
    r = s.grant_access("dev-kangi", "mkt-hyeopseong", ["작업 기록", "할 일"], requester="po-seoan")
    assert [g["항목"] for g in r["추가"]] == ["할 일"]
    assert [g["항목"] for g in r["이미 있음"]] == ["작업 기록"]
    assert r["추가"][0]["상태"] == "유효"


def test_grant_access_everyone_target(data):
    r = s.grant_access("dev-kangi", "전원", ["이슈"], requester="po-seoan")
    assert r["추가"][0]["대상"] == "전원"


def test_grant_access_rejects_unknown_item(data):
    with pytest.raises(ToolError, match="항목"):
        s.grant_access("dev-kangi", "mkt-hyeopseong", ["근무 시간"], requester="po-seoan")
    with pytest.raises(ToolError, match="팀원 목록에 없어요"):
        s.grant_access("dev-kangi", "nobody", ["이슈"], requester="po-seoan")


def test_revoke_access_keeps_row(data):
    r = s.revoke_access("1", requester="po-seoan")
    assert r["범위"]["상태"] == "회수"
    assert len(s._read("access")) == 1
    assert s.list_access(requester="po-seoan")["개수"] == 0


def test_list_access_po_only(data, monkeypatch):
    assert s.list_access(requester="po-seoan", viewer="dev-kangi")["개수"] == 1
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    with pytest.raises(ToolError, match="PO 만"):
        s.list_access(requester="dev-kangi")
