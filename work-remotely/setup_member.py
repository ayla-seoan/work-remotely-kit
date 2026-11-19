"""팀원 한 명을 이 컴퓨터의 Claude Code 에 team MCP 로 연결해요.

    python work-remotely/setup_member.py              # 팀원 아이디 목록 보기
    python work-remotely/setup_member.py dev-kangi    # 나 = dev-kangi 로 연결
    python work-remotely/setup_member.py dev-kangi --dry-run   # 실행할 명령만 보기

하는 일
  1) members.csv 에서 아이디 확인 (이름 · 직군 보여 줌)
  2) uv sync (mcp 설치)
  3) claude mcp add --scope user team  ← TEAM_ME=<아이디> 로 등록 (어느 폴더에서 claude 를 켜도 같은 '나')
  4) 내 직군이 쓰는 외부 MCP 를 추가하는 명령 안내
표준 라이브러리만 써요 (설치 전에도 실행돼요).
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def read(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]


def run(cmd: list[str], dry: bool) -> int:
    print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    if dry:
        return 0
    return subprocess.run(cmd, cwd=HERE).returncode


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    members = read("members.csv")
    if not args:
        print("팀원 아이디를 골라 실행하세요:  python work-remotely/setup_member.py <아이디>\n")
        for m in members:
            print(f"  {m['아이디']:<18} {m['이름']} · {m['직군']}")
        return 1
    me = args[0]
    member = next((m for m in members if m["아이디"] == me), None)
    if not member:
        print(f"'{me}' 는 팀원 목록(data/members.csv)에 없어요. 아이디 없이 실행하면 목록이 나와요.")
        return 1
    role = next((r for r in read("roles.csv") if r["직군"] == member["직군"]), None)
    catalog = {c["이름"]: c for c in read("mcp_catalog.csv")}
    print(f"\n안녕하세요, {member['이름']} 님 ({member['직군']} · {me})\n")

    uv = shutil.which("uv")
    if not uv:
        print("! uv 가 없어요. 먼저 설치하세요: https://docs.astral.sh/uv/getting-started/installation/")
        return 1
    print("1) 파이썬 환경 준비 (mcp 설치)")
    if run([uv, "sync", "--quiet"], dry) != 0:
        print("! uv sync 가 실패했어요. 인터넷 연결과 Python 3.10+ 를 확인하세요.")
        return 1

    print("\n2) Claude Code 에 team MCP 등록 (나 = " + me + ")")
    claude = shutil.which("claude")
    add = ["claude", "mcp", "add", "--scope", "user", "team",
           "-e", f"TEAM_ME={me}", "-e", "PYTHONUTF8=1", "--",
           "uv", "run", "--directory", str(HERE), "python", "team_server.py"]
    if not claude:
        print("! claude 명령이 없어요. Claude Code 를 설치한 뒤 아래 명령을 직접 실행하세요:")
        print("  " + " ".join(f'"{c}"' if " " in c else c for c in add))
    else:
        if not dry:
            subprocess.run([claude, "mcp", "remove", "team", "--scope", "user"], capture_output=True)  # 예전 등록 정리
        if run([claude] + add[1:], dry) != 0:
            print("! 등록이 실패했어요. 위 명령을 직접 실행해 보세요.")
            return 1

    print(f"\n3) {member['직군']} 직무가 같이 쓰는 외부 MCP (필요한 것만, 각자 로그인)")
    for name in (role["외부 MCP"].split() if role else []):
        c = catalog.get(name, {})
        if c.get("주소"):
            extra = ' --header "Authorization: Bearer ${GITHUB_PAT}"' if name == "github" else ""
            print(f"  - {name:<16} {c.get('용도', '')}\n      claude mcp add --scope user --transport http {name} {c['주소']}{extra}")
        else:
            print(f"  - {name:<16} {c.get('용도', '')}  → claude.ai › 설정 › 커넥터에서 연결")

    tools = role["team 도구"].split() if role else []
    print(f"\n끝! 이제 아무 폴더에서 claude 를 켜고 /mcp 에서 team 이 connected 인지 확인하세요.")
    print(f"내 직무에서 쓰는 team 도구 {len(tools)}개. 이렇게 말해 보세요:")
    print("  · team 으로 나는 누구야?")
    print("  · team 으로 내 할 일과 열린 이슈 보여 줘")
    print("  · 오늘 2시간 한 거 기록해 줘: ○○ (할 일 #n, 링크 https://...)  먼저 보여 줘")
    print("  · 할 일 #n 마감을 이틀 늘려 달라고 PO 에게 요청해 줘. 사유: ○○  먼저 보여 줘")
    if member["직군"] == "PO":
        print("  · 승인 대기 중인 기간 변경 요청 보여 주고, #n 승인해 줘")
        print("  · 담당자 없는 이슈 보여 주고 #n 을 ○○ 에게 맡겨 줘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
