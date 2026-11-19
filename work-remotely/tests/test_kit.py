"""설치 키트: 데이터 없는 공개 저장소용 폴더 (실제 data/ 를 읽기만 해요)."""

from pathlib import Path

import export_office
import make_kit

HERE = Path(make_kit.__file__).resolve().parent


def _lines(p: Path) -> list[str]:
    return [x for x in p.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def test_kit_has_no_real_data(tmp_path):
    make_kit.build_kit_dir(tmp_path)
    data = tmp_path / "work-remotely" / "data"
    for name in ("tasks.csv", "worklog.csv", "issues.csv", "attendance.csv", "meetings.csv", "projects.csv", "access.csv"):
        assert len(_lines(data / name)) == 1, name           # 머리줄만
    assert (data / "members.csv").read_bytes() == (HERE / "data" / "members.csv").read_bytes()
    assert (data / "roles.csv").exists() and (data / "settings.csv").exists()


def test_kit_excludes_private_files(tmp_path):
    files = make_kit.build_kit_dir(tmp_path)
    rel = {p.relative_to(tmp_path).as_posix() for p in files}
    for bad in ("work-remotely/office/office.html", "work-remotely/data/notion_sync_state.json"):
        assert bad not in rel and not (tmp_path / bad).exists()
    assert not any(r.startswith(("work-remotely/web/", "work-remotely/web-api/", "docs/")) for r in rel)
    for good in ("START_HERE.md", "work-remotely/office/template.html", "work-remotely/office/lib.js",
                 "work-remotely/setup_member.py", "work-remotely/team_server.py"):
        assert (tmp_path / good).exists(), good


def test_kit_has_no_real_emails(tmp_path):
    """공개 키트에 진짜 이메일(관리자 포함)이 없어야 해요."""
    make_kit.build_kit_dir(tmp_path)
    for p in tmp_path.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".mjs", ".md", ".csv", ".json", ".html", ".js", ".toml"):
            text = p.read_text(encoding="utf-8", errors="ignore").lower()
            assert "@" + "gmail.com" not in text, p   # 진짜 메일 주소가 섞이면 안 돼요 (테스트는 example.com 만)


def test_tracked_web_shell_has_no_data():
    """저장소에 올라가는 work-remotely/web/index.html 자체가 데이터 없는 껍데기여야 해요."""
    html = (HERE / "web" / "index.html").read_text(encoding="utf-8")
    assert '"remote": "/api/data"' in html
    assert '"preview": {' not in html


def test_vercel_config_always_deploys_and_bundles_data():
    """마지막 커밋만 보고 배포를 건너뛰면 api 고친 것이 안 올라갈 수 있어요 → 건너뛰기 규칙 없이 늘 배포."""
    import json
    cfg = json.loads((HERE.parent / "vercel.json").read_text(encoding="utf-8"))
    assert "ignoreCommand" not in cfg
    assert cfg["outputDirectory"] == "work-remotely/web"
    assert cfg["functions"]["api/data.js"]["includeFiles"] == "work-remotely/web-api/**"


def test_kit_zip_link_points_to_kit_repo():
    assert export_office.KIT_ZIP == "https://github.com/ayla-seoan/work-remotely-kit/archive/refs/heads/main.zip"
