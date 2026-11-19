"""재택 근무 도구: 출퇴근 · 휴가 · 실시간 상태 · 체크인 · 근무 시간 · 리마인더.

샘플 기준: 2026-11-17 15:00 (conftest). 이민정 연차 · 김미영 반차(오전) 승인, 김강이 11/20~21 연차 대기.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import team_server as s


def _who(result, member_id):
    return next(r for r in result["팀원"] if r["아이디"] == member_id)


# ── 근무 현황 ────────────────────────────────────────────────
def test_attendance_today_summary(data):
    result = s.attendance()
    assert result["날짜"] == "2026-11-17" and result["지금"] == "15:00"
    summary = result["요약"]
    assert summary["근무 예정"] == 6                       # 이민정 연차 빼고
    assert summary["출근"] == 5 and summary["근무 중"] == 5 and summary["퇴근"] == 0
    assert summary["휴가 · 부재"] == ["이민정(연차)"]
    assert summary["출근 기록 없음"] == ["dev-myeonggeun"]
    assert summary["체크인 제출"] == 3
    assert summary["코어 타임 벗어남"] == ["dev-jaemin"]   # 11:20 시작


def test_attendance_rows(data):
    result = s.attendance()
    kangi = _who(result, "dev-kangi")
    assert (kangi["출근"], kangi["근무지"], kangi["근무 중"]) == ("09:55", "재택", True)
    assert kangi["근무 시간"] == 5.1 and kangi["작업 기록 시간"] == 1.0 and kangi["기록 비율"] == "20%"
    assert (kangi["실시간 상태"], kangi["상태 메모"]) == ("집중", "README 마무리 · 16시까지")
    assert kangi["체크인"] is True and kangi["코어 타임"] == "지킴"
    miyoung = _who(result, "design-miyoung")
    assert miyoung["일정"] == "반차(오전)" and miyoung["코어 타임"] == "지킴"  # 오전 반차라 13시 출근도 괜찮아요
    assert _who(result, "dev-myeonggeun")["실시간 상태"] == ""              # 어제 상태는 안 보여요
    assert _who(result, "dev-jaemin")["막힘"].startswith("이슈 #1")


def test_attendance_past_day(data):
    result = s.attendance("2026-11-16")
    assert result["지금"] == ""
    kangi = _who(result, "dev-kangi")
    assert kangi["근무 중"] is False and kangi["근무 시간"] == 8.1   # 09:58~19:05, 점심 1시간 빼기
    assert _who(result, "design-minjeong")["상태"] == "근무"
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        s.attendance("어제")


def test_list_members_reflects_leave_and_attendance(data):
    rows = {m["아이디"]: m for m in s.list_members()["팀원"]}
    assert rows["design-minjeong"]["상태"] == "연차"
    assert rows["design-miyoung"]["상태"] == "근무" and rows["design-miyoung"]["오늘 일정"] == "반차(오전)"
    assert rows["dev-kangi"]["출근"] == "09:55" and rows["dev-kangi"]["실시간 상태"] == "집중"
    assert s.team_dashboard()["오늘 근무"]["출근"] == 5


# ── 출퇴근 ──────────────────────────────────────────────────
def test_check_in_and_out(data):
    result = s.check_in("dev-myeonggeun", "재택", at="10:10")
    assert result["출근"]["출근"] == "10:10" and "코어 타임" not in result
    with pytest.raises(ToolError, match="이미 10:10 출근"):
        s.check_in("dev-myeonggeun")
    out = s.check_out("dev-myeonggeun", at="19:10")
    assert out["근무 시간"] == 8.0 and out["작업 기록 시간"] == 0
    assert "기록 누락" in out
    with pytest.raises(ToolError, match="이미 19:10 퇴근"):
        s.check_out("dev-myeonggeun", at="19:20")


def test_check_in_uses_now_and_flags_late(data):
    s.attendance()  # 읽기만
    result = s.check_in("dev-myeonggeun")     # TEAM_NOW = 15:00
    assert result["출근"]["출근"] == "15:00" and "코어 타임" in result


def test_check_in_validation(data):
    with pytest.raises(ToolError, match="근무지"):
        s.check_in("dev-myeonggeun", "카페")
    with pytest.raises(ToolError, match="HH:MM"):
        s.check_in("dev-myeonggeun", at="9시")
    with pytest.raises(ToolError, match="앞날"):
        s.check_in("dev-myeonggeun", work_date="2026-11-18")
    with pytest.raises(ToolError, match="출근 기록이 없어요"):
        s.check_out("dev-myeonggeun")
    with pytest.raises(ToolError, match="늦어야"):
        s.check_out("dev-kangi", at="09:00")


def test_check_in_on_leave_warns(data):
    result = s.check_in("design-minjeong", at="10:00")
    assert "연차" in result["주의"]


def test_remote_writes_are_self_only(data, monkeypatch):
    monkeypatch.setenv("TEAM_ME", "dev-jaemin")
    for call in (lambda: s.check_in("dev-myeonggeun"), lambda: s.check_out("dev-kangi"),
                 lambda: s.set_status("dev-kangi", "집중"), lambda: s.submit_checkin("dev-kangi", "a", "b"),
                 lambda: s.request_leave("dev-kangi", "연차", "2026-11-30")):
        with pytest.raises(ToolError, match="다른 사람 이름으로는"):
            call()


# ── 실시간 상태 ──────────────────────────────────────────────
def test_set_status_updates_one_row(data):
    result = s.set_status("dev-kangi", "응답 가능", "리뷰 요청 환영")
    assert result["결과"] == "dev-kangi 상태: 집중 → 응답 가능 (리뷰 요청 환영)"
    s.set_status("dev-myeonggeun", "집중")   # 어제 상태가 있던 사람 → 오늘 것으로 바뀜
    rows = s._read("presence")
    assert sum(1 for p in rows if p["아이디"] == "dev-kangi") == 1
    assert _who(s.attendance(), "dev-kangi")["실시간 상태"] == "응답 가능"
    with pytest.raises(ToolError, match="가능한 값"):
        s.set_status("dev-kangi", "퇴근")


def test_set_status_without_check_in_hints(data):
    assert "check_in" in s.set_status("dev-myeonggeun", "집중")["안내"]


# ── 휴가 · 부재 ──────────────────────────────────────────────
def test_request_and_approve_leave_changes_state(data):
    req = s.request_leave("dev-myeonggeun", "연차", "2026-11-17", reason="몸살")
    assert req["신청"]["상태"] == "대기"
    assert _who(s.attendance(), "dev-myeonggeun")["상태"] == "근무"     # 승인 전
    s.review_leave(req["신청"]["번호"], "승인", "po-seoan")
    assert _who(s.attendance(), "dev-myeonggeun")["상태"] == "연차"
    assert "dev-myeonggeun" not in s.list_checkins()["미제출"]


def test_leave_validation(data):
    with pytest.raises(ToolError, match="가능한 값"):
        s.request_leave("dev-jaemin", "휴식", "2026-11-20")
    with pytest.raises(ToolError, match="반차는 하루만"):
        s.request_leave("dev-jaemin", "반차(오후)", "2026-11-20", "2026-11-21")
    with pytest.raises(ToolError, match="늦을 수 없어요"):
        s.request_leave("dev-jaemin", "연차", "2026-11-21", "2026-11-20")
    with pytest.raises(ToolError, match="이미 '대기'"):
        s.request_leave("dev-kangi", "외근", "2026-11-21")      # 11/20~21 연차 대기와 겹침


def test_review_leave_po_only_and_reject_needs_reason(data):
    with pytest.raises(ToolError, match="PO 가 아니라서"):
        s.review_leave("3", "승인", "dev-jaemin")
    with pytest.raises(ToolError, match="이유"):
        s.review_leave("3", "반려", "po-seoan")
    assert s.review_leave("3", "반려", "po-seoan", "출시 주간이라 다음 주로")["신청"]["상태"] == "반려"
    with pytest.raises(ToolError, match="이미 '반려'"):
        s.review_leave("3", "승인", "po-seoan")


def test_list_leaves_hides_reason_from_others(data, monkeypatch):
    assert s.list_leaves()["신청"][0]["번호"] == "3"            # 대기 먼저
    monkeypatch.setenv("TEAM_ME", "dev-jaemin")
    reasons = {lv["번호"]: lv["사유"] for lv in s.list_leaves()["신청"]}
    assert reasons["3"] == "(본인 · PO 만 보여요)"
    monkeypatch.setenv("TEAM_ME", "dev-kangi")
    assert {lv["번호"]: lv["사유"] for lv in s.list_leaves()["신청"]}["3"] == "가족 여행"
    monkeypatch.setenv("TEAM_ME", "po-seoan")
    assert all(lv["사유"] != "(본인 · PO 만 보여요)" for lv in s.list_leaves()["신청"])
    assert s.list_leaves(from_date="2026-11-18")["개수"] == 1


# ── 체크인 ──────────────────────────────────────────────────
def test_checkins(data):
    result = s.list_checkins()
    assert result["제출"] == 3
    assert result["미제출"] == ["dev-myeonggeun", "design-miyoung", "mkt-hyeopseong"]   # 이민정은 연차
    assert [c["아이디"] for c in result["막힘"]] == ["dev-jaemin"]
    saved = s.submit_checkin("mkt-hyeopseong", "페르소나 정리", "출시 공지 초안", "카피 톤 결정 필요")
    assert "create_issue" in saved["안내"]
    with pytest.raises(ToolError, match="이미 남겼어요"):
        s.submit_checkin("mkt-hyeopseong", "a", "b")
    with pytest.raises(ToolError, match="비어 있어요"):
        s.submit_checkin("design-miyoung", "a", " ")


# ── 근무 시간 · 기록 누락 ────────────────────────────────────
def test_work_hours(data):
    result = s.work_hours(days=2)
    assert result["기간"] == "2026-11-16 ~ 2026-11-17"
    kangi = _who(result, "dev-kangi")
    assert kangi["출근일"] == 2 and kangi["근무 시간"] == 13.2   # 8.1 + 5.1 (오늘은 지금까지)
    assert kangi["기록 누락일"] == ["2026-11-16"]                # 오늘은 아직 안 끝나서 빼요
    assert _who(result, "po-seoan")["퇴근 기록 없음"] == ["2026-11-16"]
    assert _who(result, "dev-myeonggeun")["날짜별"] == []
    with pytest.raises(ToolError):
        s.work_hours(days=0)


# ── 리마인더 ────────────────────────────────────────────────
def test_reminders(data):
    r = s.reminders()
    assert r["출근 기록 없음"] == ["dev-myeonggeun"]
    assert r["체크인 미제출"] == ["design-miyoung", "mkt-hyeopseong"]
    assert r["퇴근 기록 없음"] == [] and r["작업 기록 없음"] == []        # 15시라 아직
    assert [b["아이디"] for b in r["막힘"]] == ["dev-jaemin"]
    assert [t["번호"] for t in r["내일까지 마감"]] == ["5"]
    assert len(r["PO 승인 대기"]["휴가"]) == 1 and len(r["PO 승인 대기"]["기간 변경"]) == 1
    draft = r["슬랙 메시지 초안"]
    assert draft.startswith("[재택 근무 알림] 2026-11-17 15:00") and "차명근" in draft and "김재민" in draft
    assert r["알림 수"] == draft.count("\n")


def test_reminders_evening(data, monkeypatch):
    monkeypatch.setenv("TEAM_NOW", "19:30")
    r = s.reminders()
    assert set(r["퇴근 기록 없음"]) == {"dev-kangi", "dev-jaemin", "po-seoan", "design-miyoung", "mkt-hyeopseong"}
    assert set(r["작업 기록 없음"]) == {"design-miyoung", "mkt-hyeopseong"}


# ── 직군별 도구 ──────────────────────────────────────────────
def test_every_role_gets_remote_tools_and_only_po_reviews_leave(data):
    for role in ("개발", "디자인", "PO", "마케팅"):
        tools = s.tools_for_role(role)
        assert set(s.REMOTE_TOOLS_ALL) <= set(tools)
        assert ("review_leave" in tools) == (role == "PO")
        assert len(tools) == len(set(tools))
