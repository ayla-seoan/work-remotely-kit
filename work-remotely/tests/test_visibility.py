"""공개 범위 계산 (visibility.py) — 기준일 2026-11-17."""

import team_server as s
from visibility import filter_tables, scope_for

DAY = "2026-11-17"
TABLES = ("members", "tasks", "issues", "worklog", "checkins", "meetings", "extensions", "projects",
          "project_members", "access", "attendance", "leaves")


def tables():
    return {name: s._read(name) for name in TABLES}


def nums(rows):
    return {r["번호"] for r in rows}


def test_scope_co_people(data):
    sc = scope_for("dev-kangi", tables(), DAY)
    assert sc["member"] == "dev-kangi"
    assert sc["projects"] == ["1"]
    assert sc["coPeople"] == ["design-miyoung", "dev-jaemin", "dev-myeonggeun", "po-seoan"]
    assert sc["memberProjects"]["po-seoan"] == ["1", "2"]
    assert sc["grants"] == {"작업 기록": ["mkt-hyeopseong"], "할 일": [], "이슈": []}


def test_assignment_end_next_day_drops_co_people(data):
    sc = scope_for("dev-kangi", tables(), "2026-11-18")
    assert "dev-myeonggeun" not in sc["coPeople"]


def test_tasks_and_issues_by_project(data):
    t = tables()
    sc = scope_for("dev-kangi", t, DAY)
    out = filter_tables(sc, t)
    assert nums(out["tasks"]) == {"1", "2", "3", "5", "6", "10"}
    assert nums(out["issues"]) == {"1", "4", "5"}
    assert sorted(sc["taskIds"], key=int) == ["1", "2", "3", "5", "6", "10"]
    assert sorted(sc["issueIds"], key=int) == ["1", "4", "5"]


def test_worklog_other_project_hidden(data):
    t = tables()
    out = filter_tables(scope_for("dev-kangi", t, DAY), t)
    # #5 이민정 · #7 김서안 은 프로젝트 2 할 일 기록이라 안 보여요. #1 신협성은 관리자가 연 범위로 보여요.
    assert nums(out["worklog"]) == {"1", "2", "3", "4", "6", "8", "9"}


def test_grant_opens_logs_not_tasks(data):
    t = tables()
    out = filter_tables(scope_for("dev-kangi", t, DAY), t)
    assert "mkt-hyeopseong" in {w["담당자"] for w in out["worklog"]}
    assert "mkt-hyeopseong" not in {x["담당자"] for x in out["tasks"]}


def test_grant_tasks_for_everyone(data):
    t = tables()
    t["access"].append({"번호": "2", "보는 사람": "dev-kangi", "대상": "전원", "항목": "할 일", "부여자": "po-seoan",
                        "날짜": DAY, "상태": "유효"})
    out = filter_tables(scope_for("dev-kangi", t, DAY), t)
    assert len(out["tasks"]) == len(t["tasks"])


def test_revoked_grant_ignored(data):
    t = tables()
    t["access"][0]["상태"] = "회수"
    out = filter_tables(scope_for("dev-kangi", t, DAY), t)
    assert "mkt-hyeopseong" not in {w["담당자"] for w in out["worklog"]}


def test_public_scope_hides_everything(data):
    t = tables()
    out = filter_tables(scope_for("", t, DAY), t)
    for name in ("tasks", "issues", "worklog", "checkins", "meetings", "extensions", "access"):
        assert out[name] == [], name
    assert len(out["attendance"]) == len(t["attendance"])  # 출퇴근은 누구나 봐요
    assert len(out["members"]) == 7


def test_extension_reason_blank_for_others(data):
    t = tables()
    kangi = filter_tables(scope_for("dev-kangi", t, DAY), t)["extensions"]
    assert [(e["번호"], e["사유"]) for e in kangi] == [("2", "")]
    jaemin = filter_tables(scope_for("dev-jaemin", t, DAY), t)["extensions"]
    assert next(e for e in jaemin if e["번호"] == "2")["사유"].startswith("이메일 중복")
    assert t["extensions"][1]["사유"].startswith("이메일 중복")  # 입력은 그대로


def test_checkins_by_co_people(data):
    t = tables()
    minjeong = filter_tables(scope_for("design-minjeong", t, DAY), t)["checkins"]
    assert {c["아이디"] for c in minjeong} == {"po-seoan"}


def test_meetings_visible_if_attendee_or_visible_person(data):
    t = tables()
    # #1 은 김서안(같은 프로젝트) · #3 은 김미영 등이 참석해서 보여요
    assert nums(filter_tables(scope_for("dev-kangi", t, DAY), t)["meetings"]) == {"1", "2", "3"}
    # 이민정(프로젝트 2)의 동료는 김서안 · 신협성 → 세 회의 모두 김서안이 참석
    assert nums(filter_tables(scope_for("", t, DAY), t)["meetings"]) == set()


def test_access_rows_only_mine(data):
    t = tables()
    assert nums(filter_tables(scope_for("dev-jaemin", t, DAY), t)["access"]) == set()
    assert nums(filter_tables(scope_for("dev-kangi", t, DAY), t)["access"]) == {"1"}


def test_no_projects_file(data):
    t = tables()
    t["projects"], t["project_members"] = [], []
    sc = scope_for("dev-kangi", t, DAY)
    assert sc["projects"] == [] and sc["coPeople"] == []
    out = filter_tables(sc, t)
    assert {x["담당자"] for x in out["tasks"]} == {"dev-kangi"}
    assert nums(out["meetings"]) == {"1", "2"}  # 본인이 참석한 #2 + 연 범위(신협성)가 참석한 #1
