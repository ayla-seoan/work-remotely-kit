"""도구 하나하나를 파이썬 함수로 직접 불러서 결과를 확인해요 (가장 빠른 테스트)."""

import pytest
from pathlib import Path

import team_server as s
from mcp.server.mcpserver.exceptions import ToolError


# ── 읽기 ─────────────────────────────────────────────────────
def test_list_members_shows_workload(data):
    result = s.list_members()
    assert result["팀원 수"] == 7
    kangi = next(m for m in result["팀원"] if m["아이디"] == "dev-kangi")
    assert kangi["남은 할 일"] == 1           # #1 진행 중
    assert kangi["진행 중"] == 1
    assert kangi["열린 이슈"] == 1           # #5 보류 (해결된 #4 는 빠짐)
    assert kangi["최근 7일 작업 시간"] == 2.0
    assert kangi["마지막 작업일"] == "2026-11-17"


def test_list_members_filter_by_role(data):
    result = s.list_members(role="개발")
    assert {m["아이디"] for m in result["팀원"]} == {"dev-kangi", "dev-jaemin", "dev-myeonggeun"}


def test_member_status(data):
    result = s.member_status("dev-jaemin")
    assert len(result["할 일"]) == 2
    assert [i["번호"] for i in result["맡은 열린 이슈"]] == ["1"]
    assert result["최근 7일 작업 시간"] == 4.5


def test_member_status_unknown_member_raises(data):
    with pytest.raises(ToolError, match="팀원 목록에 없어요"):
        s.member_status("nobody")


def test_list_tasks_filters(data):
    assert s.list_tasks(status="완료")["개수"] == 2
    assert s.list_tasks(role="디자인", status="진행 중")["개수"] == 1
    assert s.list_tasks(assignee="없는사람")["개수"] == 0  # 에러 없이 빈 목록


def test_progress(data):
    result = s.progress()
    assert result["전체"] == "2/10 (20%)"
    assert result["직군별"]["마케팅"] == "1/2 (50%)"
    assert result["담당자별"]["po-seoan"] == "1/2 (50%)"


def test_list_issues_default_hides_resolved_and_sorts_by_severity(data):
    result = s.list_issues()
    assert [i["번호"] for i in result["이슈"]] == ["1", "2", "5", "3"]  # 긴급 → 높음 → 보통
    assert "4" not in [i["번호"] for i in result["이슈"]]


def test_list_issues_all_and_filters(data):
    assert s.list_issues(status="전체")["개수"] == 5
    assert s.list_issues(severity="높음")["개수"] == 2
    assert s.list_issues(assignee="po-seoan")["개수"] == 1


def test_get_issue_with_related_task(data):
    result = s.get_issue("#1")
    assert result["이슈"]["제목"] == "회원가입 API 500 에러"
    assert result["관련 할 일"]["할 일"] == "회원가입 API 만들기"


def test_due_soon(data):
    result = s.due_soon(1)
    assert [t["번호"] for t in result["1일 안 마감"]] == ["5"]
    assert [t["번호"] for t in result["마감 지남"]] == ["8"]  # 11/16 마감 · 진행 중


def test_work_log_window(data):
    result = s.work_log(days=7)
    assert all(w["날짜"] >= "2026-11-10" for w in result["기록"])  # 11/09 기록은 빠짐
    assert result["사람별 시간"]["dev-jaemin"] == 4.5


def test_dashboard(data):
    result = s.team_dashboard()
    assert result["열린 이슈 수"] == {"긴급": 1, "높음": 2, "보통": 1, "낮음": 0}
    assert result["진행률"]["전체"] == "2/10 (20%)"


# ── 쓰기 ─────────────────────────────────────────────────────
def test_create_issue_appends_row(data):
    result = s.create_issue("로그인 느림", "3초 이상 걸려요", "보통", reporter="po-seoan", assignee="dev-kangi")
    assert result["이슈"]["번호"] == "6"
    assert result["이슈"]["상태"] == "열림"
    assert s.get_issue("6")["이슈"]["담당자"] == "dev-kangi"
    assert s.list_issues(status="전체")["개수"] == 6  # 기존 5개는 그대로


@pytest.mark.parametrize("kwargs, message", [
    (dict(severity="엄청 급함"), "심각도"),
    (dict(reporter="nobody"), "보고자"),
    (dict(assignee="nobody"), "담당자"),
    (dict(task_id="999"), "할 일 #999"),
    (dict(title="  "), "제목"),
])
def test_create_issue_validation(data, kwargs, message):
    args = dict(title="t", description="d", severity="보통", reporter="po-seoan") | kwargs
    with pytest.raises(ToolError, match=message):
        s.create_issue(**args)
    assert s.list_issues(status="전체")["개수"] == 5  # 실패하면 아무것도 안 써요


def test_update_issue_keeps_old_notes(data):
    result = s.update_issue("1", status="해결", note="중복 체크 추가 · 409 반환")
    assert result["바뀐 것"] == {"상태": "진행 중 → 해결"}
    memo = s.get_issue("1")["이슈"]["메모"]
    assert memo.startswith("[2026-11-17] 원인")                 # 예전 메모 유지
    assert memo.endswith("[2026-11-17] 중복 체크 추가 · 409 반환")  # 새 메모 추가


def test_update_issue_needs_something(data):
    with pytest.raises(ToolError, match="하나 이상"):
        s.update_issue("1")


def test_add_task_and_update_status(data):
    task = s.add_task("결제 화면 와이어", "디자인", "design-minjeong", "2026-11-27")["할 일"]
    assert task["번호"] == "11" and task["상태"] == "할 일"
    s.update_task_status("11", "완료")
    assert s.progress()["전체"] == "3/11 (27%)"


def test_add_task_bad_date(data):
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        s.add_task("x", "개발", "dev-kangi", "다음주")


def test_update_task_status_rejects_unknown_status(data):
    with pytest.raises(ToolError, match="가능한 값"):
        s.update_task_status("1", "삭제")


def test_log_work(data):
    s.log_work("design-minjeong", "예약 플로우 와이어 2차", 2, task_id="7")
    status = s.member_status("design-minjeong")
    assert status["최근 7일 작업 시간"] == 4.5
    assert status["최근 7일 작업 기록"][0]["내용"] == "예약 플로우 와이어 2차"


@pytest.mark.parametrize("hours", [0, -1, 25])
def test_log_work_rejects_bad_hours(data, hours):
    with pytest.raises(ToolError, match="시간"):
        s.log_work("design-minjeong", "x", hours)


def test_csv_stays_readable_in_excel_encoding(data):
    s.create_issue("한글 깨짐 확인", "내용", "낮음", reporter="po-seoan", project="1")
    raw = (data / "issues.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM → 엑셀에서 한글이 안 깨져요
    assert "한글 깨짐 확인" in raw.decode("utf-8-sig")


def test_no_delete_tools_exist():
    names = [t.name for t in s.mcp._tool_manager.list_tools()]
    assert not [n for n in names if any(w in n for w in ("delete", "remove", "drop", "clear"))]


# ── 직군별 MCP 세트 ──────────────────────────────────────────
def test_role_toolkit_lists_every_role(data):
    result = s.role_toolkit()
    assert [r["직군"] for r in result["직군별"]] == ["개발", "디자인", "PO", "마케팅"]
    dev = result["직군별"][0]
    assert dev["팀원"] == ["김강이", "김재민", "차명근"]
    assert [m["이름"] for m in dev["외부 MCP"]] == ["github", "sentry", "supabase", "notion"]


def test_role_toolkit_by_key_and_unknown(data):
    assert s.role_toolkit("design")["직군별"][0]["직군"] == "디자인"
    with pytest.raises(ToolError, match="roles.csv 에 없어요"):
        s.role_toolkit("영업")


def test_roles_differ_and_reference_real_tools_and_mcps(data):
    all_tools = {fn.__name__ for fn, _, _ in s.ALL_TOOLS}
    catalog = s._catalog()
    sets = {}
    for r in s._roles():
        tools = set(r["team 도구"].split())
        assert tools <= all_tools, f"{r['직군']}: 없는 도구 {tools - all_tools}"
        assert set(r["외부 MCP"].split()) <= set(catalog), f"{r['직군']}: 카탈로그에 없는 MCP"
        sets[r["직군"]] = (frozenset(tools), frozenset(r["외부 MCP"].split()))
    assert len(set(sets.values())) == len(sets)  # 직군마다 MCP 세트가 달라요
    assert sets["PO"][0] == frozenset(all_tools)  # PO 는 팀 관리라 전부


def test_tools_for_role_accepts_name_or_key(data):
    assert s.tools_for_role("마케팅") == s.tools_for_role("mkt")
    assert "add_task" not in s.tools_for_role("개발")


# ── 일정 · 공수 · 기간 연장 ──────────────────────────────────
def _row(result, task_id):
    return next(r for r in result["할 일"] if r["번호"] == task_id)


def test_schedule_overview_flags(data):
    result = s.schedule_overview()
    summary = result["요약"]
    assert summary["예상 공수 합계"] == 43
    assert summary["실제 투입 시간"] == 14.5
    assert summary["완료 기준 진행률"] == "9%"          # (2 + 2) / 43
    assert summary["지연"] == ["8"]                     # 11/16 마감 · 진행 중
    assert summary["공수 초과"] == ["5"]                # 예상 4h · 실제 4.5h
    assert summary["연장 대기"] == ["5"]
    assert _row(result, "7")["연장됨"] is True          # 기준 11/18 → 11/19
    assert _row(result, "8")["지연 일수"] == 1
    assert _row(result, "5")["열린 이슈"] == ["1"]


def test_schedule_overview_by_role(data):
    assert {r["직군"] for r in s.schedule_overview("디자인")["할 일"]} == {"디자인"}


def test_request_extension_validation(data):
    with pytest.raises(ToolError, match="이미 대기 중"):
        s.request_extension("5", "2026-11-21", "또 필요", "dev-jaemin")
    with pytest.raises(ToolError, match="바뀐 게 없어요"):
        s.request_extension("1", "2026-11-20", "그대로", "dev-kangi")
    with pytest.raises(ToolError, match="늦을 수 없어요"):
        s.request_extension("1", "2026-11-14", "거꾸로", "dev-kangi", new_start="2026-11-16")
    with pytest.raises(ToolError, match="이미 완료"):
        s.request_extension("3", "2026-11-30", "x", "po-seoan")
    with pytest.raises(ToolError, match="사유"):
        s.request_extension("1", "2026-11-22", " ", "dev-kangi")


def test_extension_approve_moves_due_and_keeps_baseline(data):
    req = s.request_extension("1", "2026-11-22", "리뷰 반영", "dev-kangi")["신청"]
    assert req["상태"] == "대기"
    with pytest.raises(ToolError, match="PO 가 아니라서"):
        s.review_extension(req["번호"], "승인", "dev-jaemin")
    s.review_extension(req["번호"], "승인", "po-seoan", "OK")
    task = next(t for t in s.list_tasks()["할 일"] if t["번호"] == "1")
    assert task["마감"] == "2026-11-22" and task["기준 마감"] == "2026-11-20"
    assert _row(s.schedule_overview(), "1")["연장됨"] is True
    with pytest.raises(ToolError, match="이미 '승인'"):
        s.review_extension(req["번호"], "반려", "po-seoan")


def test_extension_reject_keeps_due(data):
    s.review_extension("2", "반려", "po-seoan", "이슈 #1 먼저")
    task = next(t for t in s.list_tasks()["할 일"] if t["번호"] == "5")
    assert task["마감"] == "2026-11-18"
    assert s.list_extensions("반려")["개수"] == 1


def test_add_task_with_schedule(data):
    task = s.add_task("결제 API", "개발", "dev-kangi", "2026-11-28", start="2026-11-24", estimate_hours=5)["할 일"]
    assert task["기준 마감"] == "2026-11-28" and task["예상 시간"] == "5"
    with pytest.raises(ToolError, match="마감"):
        s.add_task("x", "개발", "dev-kangi", "2026-11-20", start="2026-11-25")


def test_log_work_link(data):
    entry = s.log_work("dev-kangi", "PR 올림", 1, task_id="1", link="https://github.com/x/y/pull/1")["기록"]
    assert entry["링크"] == "https://github.com/x/y/pull/1"
    assert s.work_log(member_id="dev-kangi")["기록"][0]["링크"] == "https://github.com/x/y/pull/1"
    with pytest.raises(ToolError, match="https://"):
        s.log_work("dev-kangi", "x", 1, link="javascript:alert(1)")


def test_change_request_shorten_and_move(data):
    short = s.request_extension("1", "2026-11-19", "일찍 끝날 듯", "dev-kangi")
    assert short["종류"] == "단축 -1일"
    s.review_extension(short["신청"]["번호"], "승인", "po-seoan")
    moved = s.request_extension("6", "2026-11-26", "선행 작업 지연", "dev-myeonggeun", new_start="2026-11-21")
    assert moved["종류"] == "연장 +2일"
    s.review_extension(moved["신청"]["번호"], "승인", "po-seoan")
    tasks = {t["번호"]: t for t in s.list_tasks()["할 일"]}
    assert (tasks["1"]["마감"], tasks["1"]["기준 마감"]) == ("2026-11-19", "2026-11-20")
    assert (tasks["6"]["시작"], tasks["6"]["마감"]) == ("2026-11-21", "2026-11-26")
    row1 = next(r for r in s.schedule_overview()["할 일"] if r["번호"] == "1")
    assert row1["기간 변경됨"] is True and row1["연장됨"] is False


# ── 담당 지정은 PO 만 ────────────────────────────────────────
def test_unassigned_issue_listed_on_dashboard(data):
    need = s.team_dashboard()["담당 지정 필요"]
    assert [i["번호"] for i in need] == ["3"]


def test_non_po_cannot_assign(data):
    with pytest.raises(ToolError, match="PO 가 아니라서"):
        s.assign_issue("3", "mkt-hyeopseong", "dev-kangi")
    with pytest.raises(ToolError, match="담당 지정은 PO"):
        s.create_issue("버그", "x", "낮음", reporter="dev-kangi", assignee="dev-jaemin")
    created = s.create_issue("버그", "x", "낮음", reporter="dev-kangi")
    assert "담당 지정이 필요" in created["결과"]


def test_po_assigns_and_note_is_kept(data):
    s.assign_issue("3", "mkt-hyeopseong", "po-seoan", "출시 공지 교차 검토")
    issue = s.get_issue("3")["이슈"]
    assert issue["담당자"] == "mkt-hyeopseong"
    assert "담당 지정: 없음 → mkt-hyeopseong (출시 공지 교차 검토)" in issue["메모"]
    assert s.team_dashboard()["담당 지정 필요"] == []
    with pytest.raises(ToolError, match="이미 해결"):
        s.assign_issue("4", "dev-kangi", "po-seoan")


# ── TEAM_ME: 누가 누구로 쓰는지 ──────────────────────────────
def test_whoami_without_me(data):
    result = s.whoami()
    assert result["나"] is None and len(result["팀원 아이디"]) == 7


def test_whoami_and_self_only_writes(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-jaemin")
    who = s.whoami()
    assert who["나"]["이름"] == "김재민" and who["직군 MCP"]["직군"] == "개발"
    s.log_work("dev-jaemin", "내 기록", 1)                       # 본인은 OK
    with pytest.raises(ToolError, match="다른 사람 이름으로는"):
        s.log_work("dev-kangi", "남의 기록", 1)
    with pytest.raises(ToolError, match="다른 사람 이름으로는"):
        s.request_extension("1", "2026-11-22", "x", "dev-kangi")
    with pytest.raises(ToolError, match="다른 사람 이름으로는"):
        s.review_extension("2", "승인", "po-seoan")            # PO 행세 불가


def test_whoami_unknown_me(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "nobody")
    with pytest.raises(ToolError, match="members.csv 에 없어요"):
        s.whoami()


# ── 회의 ────────────────────────────────────────────────────
def test_list_meetings_and_dashboard(data):
    result = s.list_meetings()
    assert [m["번호"] for m in result["회의"]] == ["3", "2", "1"]          # 최신 먼저
    assert len(result["회의"][1]["참석자"]) == 7
    assert [m["번호"] for m in s.list_meetings(member_id="mkt-hyeopseong")["회의"]] == ["2", "1"]
    assert [m["제목"] for m in s.team_dashboard()["오늘 회의"]] == ["데일리 스탠드업", "예약 플로우 디자인 리뷰"]


def test_log_meeting(data):
    row = s.log_meeting("주간 회고", "po-seoan, dev-kangi", "po-seoan", "17:00", "17:30",
                        decisions="다음 주 목표 3개", link="https://app.notion.com/p/x")["회의"]
    assert row["참석자"] == "po-seoan dev-kangi" and row["날짜"] == "2026-11-17"
    everyone = s.log_meeting("전체 공유", "전원", "po-seoan", "18:00", "18:10")["회의"]
    assert len(everyone["참석자"].split()) == 7


@pytest.mark.parametrize("kwargs, message", [
    (dict(attendees="nobody"), "참석자"),
    (dict(start="15:00", end="14:00"), "늦어야"),
    (dict(start="3pm"), "HH:MM"),
    (dict(link="http://x"), "https://"),
    (dict(attendees=" "), "한 명 이상"),
])
def test_log_meeting_validation(data, kwargs, message):
    args = dict(title="회의", attendees="po-seoan", recorder="po-seoan", start="10:00", end="11:00") | kwargs
    with pytest.raises(ToolError, match=message):
        s.log_meeting(**args)


def test_log_meeting_self_only(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    with pytest.raises(ToolError, match="다른 사람 이름으로는"):
        s.log_meeting("회의", "dev-kangi", "po-seoan", "10:00", "11:00")


# ── 회의록 규칙: 노션 정본 · 중복 막기 ─────────────────────────
def test_same_meeting_link_only_once(data):
    link = "https://app.notion.com/p/abc"
    s.log_meeting("회고", "po-seoan", "po-seoan", "17:00", "17:30", link=link)
    with pytest.raises(ToolError, match="이미 회의 #"):
        s.log_meeting("회고 다시", "po-seoan", "po-seoan", "17:00", "17:30", link=link)


def test_import_meetings_prompt_uses_notion_db(data):
    text = s.import_meetings()
    assert "app.notion.com/p/41bb77b7c99a81ce8a88d05995cb0d6e" in text
    assert "'완료'" in text and "team 기록" in text and "log_meeting" in text


# ── 노션 → CSV 배치 ──────────────────────────────────────────
def test_update_task_po_only_and_keeps_baseline(data):
    with pytest.raises(ToolError, match="PO 가 아니라서"):
        s.update_task("2", "dev-kangi", assignee="design-minjeong")
    r = s.update_task("2", "po-seoan", assignee="design-minjeong", due="2026-11-22", estimate_hours=7)
    assert r["바뀐 것"]["담당자"] == "design-miyoung → design-minjeong"
    t = next(t for t in s.list_tasks()["할 일"] if t["번호"] == "2")
    assert (t["마감"], t["기준 마감"], t["예상 시간"]) == ("2026-11-22", "2026-11-20", "7")
    assert s.update_task("2", "po-seoan", due="2026-11-22")["바뀐 것"] == {}


def test_sync_notion_script(data, tmp_path, monkeypatch):
    import json, subprocess, sys as _sys, os
    rows = {"results": [
        {"할 일": "메인 화면 와이어 설명", "번호": "2", "직군": "디자인", "담당": "이민정 · design-minjeong", "상태": "진행 중",
         "date:기간:start": "2026-11-17", "date:기간:end": "2026-11-22", "예상 공수": 6, "url": "u2"},
        {"할 일": "결제 화면 와이어", "번호": "", "직군": "디자인", "담당": "김미영 · design-miyoung", "상태": "할 일",
         "date:기간:start": "2026-11-21", "date:기간:end": "2026-11-26", "예상 공수": 5, "url": "u-new"},
        {"할 일": "README에 실행 방법 정리", "번호": "1", "직군": "개발", "담당": "김강이 · dev-kangi", "상태": "진행 중",
         "date:기간:start": "2026-11-13", "date:기간:end": "2026-11-20", "예상 공수": 4, "url": "u1"},
    ]}
    f = tmp_path / "rows.json"
    f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    script = Path(s.__file__).with_name("sync_notion_tasks.py")
    env = {**os.environ, "TEAM_ME": "po-seoan", "PYTHONUTF8": "1"}
    out = json.loads(subprocess.run([_sys.executable, str(script), str(f)], capture_output=True, text=True, env=env, encoding="utf-8").stdout)
    assert [c["번호"] for c in out["changed"]] == ["2"]            # #1 은 같아서 그대로
    assert out["changed"][0]["assignee"] == "design-minjeong" and out["changed"][0]["status"] == "진행 중"
    assert out["created"][0]["번호"] == "11" and out["created"][0]["url"] == "u-new"
    again = json.loads(subprocess.run([_sys.executable, str(script), str(f)], capture_output=True, text=True, env=env, encoding="utf-8").stdout)
    assert again["changed"] == []                                    # 두 번 돌려도 같은 결과


# ── 대시보드 → 노션 계획 ─────────────────────────────────────
def test_plan_dashboard_to_notion():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plan", Path(s.__file__).with_name("plan_dashboard_to_notion.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    notion = [
        {"번호": "2", "할 일": "메인 화면 와이어 설명", "담당": "김미영 · design-miyoung", "상태": "할 일",
         "date:기간:start": "2026-11-17", "date:기간:end": "2026-11-20", "예상 공수": 6, "url": "u2"},
        {"번호": "6", "할 일": "클래스 목록 화면 컴포넌트", "담당": "차명근 · dev-myeonggeun", "상태": "할 일",
         "date:기간:start": "2026-11-19", "date:기간:end": "2026-11-24", "예상 공수": 8, "url": "u6"},
    ]
    data = {
        "members": {"design-minjeong": "이민정", "design-miyoung": "김미영", "dev-kangi": "김강이"},
        "notion": notion,
        "taskEdits": {
            "2": {"assignee": "design-minjeong", "due": "2026-11-22", "start": "2026-11-17", "estimate": 6},
            "t9x": {"title": "결제 API", "role": "개발", "assignee": "dev-kangi", "start": "2026-11-24", "due": "2026-11-28", "estimate": 6},
            "tbad": {"title": "", "role": "개발"},
        },
        "events": [
            {"id": "e1", "type": "task_status", "task": "6", "status": "진행 중", "at": "2026-11-17T01:00:00Z"},
            {"id": "e2", "type": "task_status", "task": "6", "status": "완료", "at": "2026-11-17T02:00:00Z"},
            {"id": "e3", "type": "worklog", "task": "6", "at": "2026-11-17T02:00:00Z"},
        ],
        "done": [],
    }
    out = mod.plan(data)
    ops = {a.get("번호") or a.get("id"): a for a in out["actions"]}
    assert ops["2"]["op"] == "update" and ops["2"]["properties"]["담당"] == "이민정 · design-minjeong"
    assert ops["2"]["properties"]["date:기간:end"] == "2026-11-22" and "예상 공수" not in ops["2"]["properties"]
    assert ops["6"]["properties"] == {"상태": "완료"}                       # 최신 상태만
    assert ops["t9x"]["op"] == "create" and ops["t9x"]["properties"]["담당"] == "김강이 · dev-kangi"
    assert set(out["done"]) == {"task:2", "task:t9x", "e1", "e2"} and out["skipped"][0]["id"] == "tbad"
    again = mod.plan({**data, "done": out["done"] + ["task:tbad"]})       # 보낸 뒤엔 다시 안 보냄
    assert again["actions"] == []


# ── CSV ↔ 노션 양방향 (스냅샷) ────────────────────────────────
def _nrow(num, **kw):
    base = {"번호": num, "할 일": "메인 화면 와이어 설명", "직군": "디자인", "담당": "김미영 · design-miyoung", "상태": "할 일",
            "date:기간:start": "2026-11-17", "date:기간:end": "2026-11-20", "예상 공수": 6, "url": f"u{num}"}
    base.update(kw)
    return base


def test_two_way_sync_with_snapshot(data, tmp_path):
    import json, os, subprocess, sys as _sys
    import importlib.util
    here = Path(s.__file__).parent
    spec = importlib.util.spec_from_file_location("pc", here / "plan_csv_to_notion.py")
    pc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pc)
    env = {**os.environ, "TEAM_ME": "po-seoan", "PYTHONUTF8": "1"}
    run = lambda rows: json.loads(subprocess.run([_sys.executable, str(here / "sync_notion_tasks.py"), str(_dump(tmp_path, rows))],
                                                 capture_output=True, text=True, env=env, encoding="utf-8").stdout)
    members = {"design-miyoung": "김미영", "design-minjeong": "이민정"}
    # 1) 첫 동기화: 노션 = CSV → 스냅샷 생김, 노션으로 보낼 것 없음
    rows = [_nrow("2")]
    assert run(rows)["changed"] == []
    state = json.loads((data / "notion_sync_state.json").read_text(encoding="utf-8"))
    assert state["2"]["담당자"] == "design-miyoung"
    # 2) Claude Code 로 CSV 만 바꿈 (담당 · 마감) → 노션으로 보낼 목록, 노션→CSV 는 되돌리지 않음
    s.update_task("2", "po-seoan", assignee="design-minjeong", due="2026-11-22")
    tasks = s.list_tasks()["할 일"]
    out = pc.plan(rows, tasks, state, members)
    assert out["actions"][0]["op"] == "update"
    assert out["actions"][0]["properties"]["담당"] == "이민정 · design-minjeong"
    assert out["actions"][0]["properties"]["date:기간:end"] == "2026-11-22"
    assert run(rows)["changed"] == []                         # 노션 옛 값이 CSV 를 덮지 않음
    assert next(t for t in s.list_tasks()["할 일"] if t["번호"] == "2")["담당자"] == "design-minjeong"
    # 3) 노션도 반영된 뒤 → 보낼 것 없음
    synced = [_nrow("2", 담당="이민정 · design-minjeong", **{"date:기간:end": "2026-11-22"})]
    run(synced)
    state = json.loads((data / "notion_sync_state.json").read_text(encoding="utf-8"))
    assert pc.plan(synced, s.list_tasks()["할 일"], state, members)["actions"] == []
    # 4) 둘 다 바꾸면 노션이 이김
    s.update_task("2", "po-seoan", title="CSV 이름")
    both = [_nrow("2", **{"할 일": "노션 이름", "담당": "이민정 · design-minjeong", "date:기간:end": "2026-11-22"})]
    assert pc.plan(both, s.list_tasks()["할 일"], state, members)["actions"] == []
    run(both)
    assert next(t for t in s.list_tasks()["할 일"] if t["번호"] == "2")["할 일"] == "노션 이름"
    # 5) CSV 에만 있는 할 일 → 노션에 번호와 함께 만들기
    new = s.add_task("결제 API", "개발", "dev-kangi", "2026-11-28", start="2026-11-24", estimate_hours=6)["할 일"]
    out = pc.plan(both, s.list_tasks()["할 일"], state, members)
    created = [a for a in out["actions"] if a["op"] == "create" and a["번호"] == new["번호"]]
    assert created and created[0]["properties"]["할 일"] == "결제 API"


def _dump(tmp_path, rows):
    import json
    f = tmp_path / f"rows_{len(list(tmp_path.iterdir()))}.json"
    f.write_text(json.dumps({"results": rows}, ensure_ascii=False), encoding="utf-8")
    return f


def test_task_tools_return_notion_hint(data):
    hint = s.update_task_status("1", "완료")["노션 반영"]
    assert hint["번호"] == "1" and hint["properties"]["상태"] == "완료" and hint["properties"]["담당"] == "김강이 · dev-kangi"
    new = s.add_task("결제 API", "개발", "dev-kangi", "2026-11-28", start="2026-11-24", estimate_hours=6)
    assert new["노션 반영"]["properties"]["date:기간:end"] == "2026-11-28" and new["노션 반영"]["properties"]["번호"] == new["할 일"]["번호"]
    approved = s.review_extension("2", "승인", "po-seoan")
    assert approved["노션 반영"]["properties"]["date:기간:end"] == "2026-11-20"


# ── 노션 '할 일 관리' 의 프로젝트 칸 ─────────────────────────
def test_notion_project_roundtrip():
    from notion_sync_common import from_notion, to_notion_props
    assert from_notion({"프로젝트": "앱 출시 · 1"})["프로젝트"] == "1"
    assert from_notion({})["프로젝트"] == ""
    assert to_notion_props({"프로젝트": "1"}, {}, {"1": "앱 출시"})["프로젝트"] == "앱 출시 · 1"
    assert to_notion_props({"프로젝트": "3"}, {}, {})["프로젝트"] == "3"
    assert "프로젝트" not in to_notion_props({"프로젝트": ""}, {}, {"1": "앱 출시"})


def test_update_task_project(data):
    r = s.update_task("2", "po-seoan", project="2")
    assert r["할 일"]["프로젝트"] == "2"
    with pytest.raises(ToolError, match="프로젝트 '9'"):
        s.update_task("2", "po-seoan", project="9")


def test_sync_creates_task_with_notion_project(data, tmp_path):
    import json, os, subprocess, sys as _sys
    rows = {"results": [_nrow("", **{"할 일": "브랜드 시안", "프로젝트": "브랜드 리뉴얼 · 2", "url": "u-b"})]}
    f = tmp_path / "rows.json"
    f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "TEAM_ME": "po-seoan", "PYTHONUTF8": "1"}
    out = json.loads(subprocess.run([_sys.executable, str(Path(s.__file__).with_name("sync_notion_tasks.py")), str(f)],
                                    capture_output=True, text=True, env=env, encoding="utf-8").stdout)
    num = out["created"][0]["번호"]
    assert next(t for t in s.list_tasks()["할 일"] if t["번호"] == num)["프로젝트"] == "2"


def test_plan_csv_pushes_project_after_migration(data):
    import importlib.util
    from notion_sync_common import from_csv
    spec = importlib.util.spec_from_file_location("pc", Path(s.__file__).with_name("plan_csv_to_notion.py"))
    pc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pc)
    task = next(t for t in s._read("tasks") if t["번호"] == "2")
    old = {k: v for k, v in from_csv(task).items() if k != "프로젝트"}       # 프로젝트 칸이 생기기 전 스냅샷
    out = pc.plan([_nrow("2", **{"담당": "김미영 · design-miyoung"})], [task], {"2": old}, {"design-miyoung": "김미영"}, {"1": "앱 출시"})
    assert out["actions"] == [{"op": "update", "page_id": "u2", "번호": "2", "properties": {"프로젝트": "앱 출시 · 1"}}]


def test_dashboard_edit_project_to_notion():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plan", Path(s.__file__).with_name("plan_dashboard_to_notion.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.notion_props({"project": "2"}, {}, {"2": "브랜드 리뉴얼"}) == {"프로젝트": "브랜드 리뉴얼 · 2"}
