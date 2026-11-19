"""팀원에게 나눠 줄 설치 키트를 만들어요 — 실제 업무 데이터는 빼요.

    uv run python make_kit.py                 # dist/work-remotely-kit.zip
    uv run python make_kit.py --dir <폴더>     # 공개 키트 저장소(ayla-seoan/work-remotely-kit)에 올릴 폴더

키트에는 코드 · 문서 · 설정과 명단(members · roles · mcp_catalog · settings)만 들어가요.
할 일 · 이슈 · 작업 기록 같은 표는 머리줄만 있는 빈 파일이고, 오피스 화면 결과 · 웹 화면 · 문서 폴더는 넣지 않아요.

먼저 export_office.py 로 roles/ · members/ 설정 파일과 대시보드를 새로 만든 뒤 묶어요.
.venv · 캐시 · 임시 파일은 넣지 않아요.
"""

import csv
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import export_office

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "dist" / "work-remotely-kit.zip"
INCLUDE = [
    "team_server.py", "export_office.py", "setup_member.py", "make_kit.py", "sync_notion_tasks.py", "plan_dashboard_to_notion.py", "plan_csv_to_notion.py", "notion_sync_common.py",
    "pyproject.toml", "uv.lock", "README.md", "TESTING.md",
    "tests/*.py", "tests/fixtures/*.csv", "roles/*.json", "members/*.json", "office/template.html", "office/lib.js",
    "visibility.py", "tests/*.mjs", "kit/*.md",
]
KIT_DATA_KEEP = ("members.csv", "roles.csv", "mcp_catalog.csv", "settings.csv")  # 원래 누구나 보는 명단 · 설정


def read(name):
    with (HERE / "data" / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def start_here() -> str:
    roles = {r["직군"]: r for r in read("roles.csv")}
    rows = []
    for m in read("members.csv"):
        r = roles.get(m["직군"], {})
        count = len(export_office.s.tools_for_role(m["직군"])) if r else 0  # roles.csv + 재택 근무 도구
        rows.append(f"| {m['이름']} | `{m['아이디']}` | {m['직군']} | {count}개 | {' · '.join(r.get('외부 MCP', '').split())} |")
    return (HERE / "kit" / "START_HERE.md").read_text(encoding="utf-8").replace("{{MEMBER_ROWS}}", "\n".join(rows))


def build_kit_dir(out: Path) -> list[Path]:
    """out/ 에 키트를 펼쳐요: START_HERE.md · README.md · CLAUDE.md · work-remotely/… (데이터는 명단만)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def put(dst: Path, src: Path | None = None, text: str | None = None) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if text is not None:
            dst.write_text(text, encoding="utf-8")
        else:
            shutil.copyfile(src, dst)
        written.append(dst)

    guide = start_here()
    put(out / "START_HERE.md", text=guide)
    put(out / "README.md", text=guide)
    if (HERE.parent / "CLAUDE.md").exists():
        put(out / "CLAUDE.md", HERE.parent / "CLAUDE.md")
    for p in sorted({p for pattern in INCLUDE for p in HERE.glob(pattern) if p.is_file()}):
        put(out / "work-remotely" / p.relative_to(HERE), p)
    data = out / "work-remotely" / "data"
    for name in KIT_DATA_KEEP:
        if (HERE / "data" / name).exists():
            put(data / name, HERE / "data" / name)
    for table, fields in export_office.s.FIELDS.items():
        if f"{table}.csv" in KIT_DATA_KEEP:
            continue
        dst = data / f"{table}.csv"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(fields)
        written.append(dst)
    return written


def main() -> None:
    if "--dir" in sys.argv:
        i = sys.argv.index("--dir")
        if i + 1 >= len(sys.argv):
            raise SystemExit("--dir 뒤에 폴더를 적어 주세요.")
        files = build_kit_dir(Path(sys.argv[i + 1]))
        print(f"키트 폴더를 만들었어요: {sys.argv[i + 1]}  (파일 {len(files)}개)")
        return
    export_office.main()  # 최신 설정 · 대시보드
    guide = start_here()
    for name in ("START_HERE.md", "README.md"):  # 레포 맨 위 안내도 최신 팀원 표로
        (HERE.parent / name).write_text(guide, encoding="utf-8")
    OUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        files = build_kit_dir(Path(tmp))
        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, f"work-remotely-kit/{p.relative_to(tmp).as_posix()}")
    print(f"만들었어요: {OUT}  (파일 {len(files)}개, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
