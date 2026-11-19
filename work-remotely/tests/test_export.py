"""오피스 화면 내보내기: 전체 · 공개 · 사람별 스냅샷 (기준일 2026-11-17)."""

import hashlib

import export_office as ex


def _hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


def _att(snap, member):
    return next(m for m in snap["attendance"]["팀원"] if m["아이디"] == member)


def test_view_hides_other_project_tasks(data):
    v = ex.snapshot_for("dev-kangi")
    assert v["tasks"] and {t["프로젝트"] for t in v["tasks"]} == {"1"}
    assert {w["번호"] for w in v["work_log"]["기록"]} == {"1", "2", "3", "4", "6", "8", "9"}
    assert v["scope"]["member"] == "dev-kangi"


def test_view_keeps_attendance_times(data):
    full, v = ex.snapshot(), ex.snapshot_for("dev-kangi")
    assert _att(v, "mkt-hyeopseong")["출근"] == _att(full, "mkt-hyeopseong")["출근"]
    assert _att(v, "design-minjeong")["체크인"] is None     # 체크인 내용은 같은 프로젝트 · 연 범위만
    assert _att(v, "mkt-hyeopseong")["체크인"] is False     # 신협성은 관리자가 연 범위 → 미제출이 그대로 보여요
    assert _att(v, "dev-jaemin")["체크인"] is True           # 같은 프로젝트 동료
    day = v["attendance_by_day"]["2026-11-17"]["팀원"]
    assert next(m for m in day if m["아이디"] == "design-minjeong")["체크인"] is None


def test_hidden_people_are_unknown_not_zero(data):
    """볼 수 없는 사람의 기록 숫자는 0 이 아니라 None (화면은 '비공개') — 거짓 '미제출 · 누락' 이 나오면 안 돼요."""
    v = ex.snapshot_for("dev-kangi")
    minjeong = _att(v, "design-minjeong")
    assert minjeong["작업 기록 시간"] is None and minjeong["기록 비율"] is None
    assert _att(v, "dev-jaemin")["작업 기록 시간"] == _att(ex.snapshot(), "dev-jaemin")["작업 기록 시간"]
    wh = next(m for m in v["work_hours"]["팀원"] if m["아이디"] == "design-minjeong")
    assert wh["작업 기록 시간"] is None and wh["기록 비율"] is None and wh["기록 누락일"] is None
    assert all(d["기록 누락"] is None and d["작업 기록 시간"] is None for d in wh["날짜별"])
    lm = next(m for m in v["list_members"]["팀원"] if m["아이디"] == "design-minjeong")
    assert lm["최근 7일 작업 시간"] is None
    assert v["member_status"]["design-minjeong"]["최근 7일 작업 시간"] is None


def test_public_view_has_no_false_missing(data):
    p = ex.snapshot_for("")
    assert p["list_checkins"]["미제출"] == []
    assert p["attendance"]["요약"]["체크인 대상"] == 0
    assert all(m["작업 기록 시간"] is None for m in p["work_hours"]["팀원"])
    kangi = ex.snapshot_for("dev-kangi")
    assert set(kangi["list_checkins"]["미제출"]) <= {"dev-kangi", "design-miyoung", "dev-jaemin", "dev-myeonggeun", "po-seoan", "mkt-hyeopseong"}
    assert "design-minjeong" not in kangi["list_checkins"]["미제출"]
    assert "체크인 대상" not in ex.snapshot()["attendance"]["요약"]


def test_view_reminders_own_only(data):
    r = ex.snapshot_for("dev-jaemin")["reminders"]
    assert r["PO 승인 대기"] == {"휴가": [], "기간 변경": []}
    assert r["슬랙 메시지 초안"] == ""
    assert [b["아이디"] for b in r["막힘"]] == ["dev-jaemin"]
    assert r["출근 기록 없음"] == []
    assert r["알림 수"] == 2  # 막힘 1 + 내일까지 마감 1 (#5)


def test_public_view_has_no_restricted(data):
    p = ex.snapshot_for("")
    assert p["work_log"]["기록"] == []
    assert p["tasks"] == []
    assert p["list_issues"]["이슈"] == []
    assert p["list_meetings"]["회의"] == []
    assert p["reminders"]["알림 수"] == 0
    assert len(p["attendance"]["팀원"]) == 7


def test_export_does_not_touch_data_dir(data):
    before = _hashes(data)
    ex.build_payload()
    assert _hashes(data) == before


def test_payload_shape(data):
    p = ex.build_payload()
    assert set(p["views"]) == {"dev-kangi", "dev-jaemin", "dev-myeonggeun", "design-miyoung", "design-minjeong",
                               "po-seoan", "mkt-hyeopseong"}
    assert p["full"]["scope"] is None
    assert p["public"]["scope"]["member"] == ""
    assert len(p["full"]["tasks"]) == 10


def test_web_shell_has_no_data(data, tmp_path):
    """Vercel 정적 화면에는 데이터가 없고 /api/data 를 불러요."""
    out = tmp_path / "web" / "index.html"
    ex.write_web(out)
    html = out.read_text(encoding="utf-8")
    assert "/*__SNAPSHOT__*/" not in html and "/*__LIB__*/" not in html
    assert '"remote": "/api/data"' in html and ex.WEB_NOTE in html
    assert "김미영" not in html and "메인 화면 와이어 설명" not in html


def test_web_api_views(data, tmp_path):
    ex.write_web_api(tmp_path, emails={})
    import json
    kangi = json.loads((tmp_path / "views" / "dev-kangi.json").read_text(encoding="utf-8"))
    full = json.loads((tmp_path / "full.json").read_text(encoding="utf-8"))
    assert kangi["preview"]["scope"]["member"] == "dev-kangi" and kangi["note"] == ex.WEB_NOTE
    assert full["preview"]["scope"] is None and full["note"] == ex.WEB_NOTE
    assert len(list((tmp_path / "views").glob("*.json"))) == 7


def test_accounts_hashed(data, tmp_path):
    import json
    ex.write_web_api(tmp_path, emails={"dev-kangi": " Kangi@Example.com ", "nobody": "x@y.z"})
    raw = (tmp_path / "accounts.json").read_text(encoding="utf-8")
    assert json.loads(raw) == {ex.email_hash("kangi@example.com"): "dev-kangi"}
    assert "@" not in raw
    assert ex.email_hash(" Admin@Example.com ") == "258d8dc916db8cea2cafb6c3cd0cb0246efe061421dbd83ec3a350428cabda4f"  # api.test.mjs 와 같은 값


def test_accounts_kept_without_secrets(data, tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "SECRETS", tmp_path / "none.json")
    (tmp_path / "accounts.json").write_text('{"abc": "dev-kangi"}', encoding="utf-8")
    ex.write_web_api(tmp_path)
    assert (tmp_path / "accounts.json").read_text(encoding="utf-8") == '{"abc": "dev-kangi"}'


def test_preview_payload_single_view(data):
    p = ex.build_payload(only="dev-kangi")
    assert p["views"] == {} and p["full"] is None and p["public"] is None
    assert p["preview"]["scope"]["member"] == "dev-kangi"
    assert ex.build_payload(only="full")["preview"]["scope"] is None
    assert ex.build_payload(only="public")["preview"]["scope"]["member"] == ""
