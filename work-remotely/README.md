# team — 팀원 · 프로젝트 · 이슈 관리 MCP

팀원과 할 일, 이슈, 작업 기록을 한곳에서 보고 관리하는 **나만의 MCP 서버**예요.
Claude 에게 "팀 상황 어때?", "민준이 요즘 뭐 해?", "긴급 이슈 보여 줘", "오늘 2시간 한 거 기록해 줘" 처럼 말하면 이 서버의 도구를 골라 써요.

```
Claude Code ──(stdio)── team_server.py ──읽기/쓰기── data/*.csv
                         도구 35개 · 리소스 1개 · 프롬프트 5개
```

## 1. 무엇을 할 수 있나요

| 하고 싶은 일 | 도구 | 쓰기? |
|---|---|---|
| 팀 전체 현황 한눈에 (진행률 · 급한 이슈 · 마감 · 팀원별 부하) | `team_dashboard` | 읽기 |
| 팀원 목록 + 각자 남은 일 · 열린 이슈 · 최근 7일 작업 시간 | `list_members` | 읽기 |
| 한 사람이 맡은 일 · 이슈 · 최근 한 일 | `member_status` | 읽기 |
| 할 일 거르기 (담당자 · 상태 · 직군) | `list_tasks` | 읽기 |
| 진행률 (전체 · 직군별 · 담당자별) | `progress` | 읽기 |
| 이슈 목록 (급한 순, 기본은 해결 안 된 것만) | `list_issues` | 읽기 |
| 이슈 하나 자세히 + 관련 할 일 | `get_issue` | 읽기 |
| N일 안 마감 · 마감 지난 할 일 | `due_soon` | 읽기 |
| 최근 작업 기록 · 사람별 시간 | `work_log` | 읽기 |
| 이슈 등록 | `create_issue` | ✏️ 추가 |
| 이슈 상태 · 담당자 변경, 메모 덧붙이기 | `update_issue` | ✏️ 수정 |
| 할 일 추가 | `add_task` | ✏️ 추가 |
| 할 일 상태 변경 | `update_task_status` | ✏️ 수정 |
| 한 일 기록 | `log_work` | ✏️ 추가 |
| 재택 근무 (출퇴근 · 상태 · 휴가 · 체크인 · 근무 시간 · 알림) | 아래 13번 | |

- **리소스** `team://members`: 팀원 명단 원문(CSV)
- **프롬프트** `standup(member_id)`: 스탠드업 초안 / `weekly_report()`: 주간 보고 초안

## 2. 일부러 만들지 않은 것 (안전 설계)

| 없는 것 · 막은 것 | 이유 |
|---|---|
| **지우기 도구가 없어요** | 이슈는 `해결`, 할 일은 `완료` 로 바꿔요. AI 가 실수해도 기록이 사라지지 않아요. |
| 메모는 **덧붙이기만** 돼요 | 처리 이력이 남아요 (`[날짜] 내용 / [날짜] 내용`). |
| 정해진 값만 받아요 | 없는 팀원 · 이상한 상태 · 날짜 형식 오류는 에러 메시지로 돌려보내고 **아무것도 쓰지 않아요**. |
| 읽기 전용 모드 | `TEAM_READONLY=1` 이면 쓰기 도구 5개를 아예 등록하지 않아요. 처음 써 볼 때나 발표할 때 쓰세요. |
| 파일 안전 쓰기 | 임시 파일에 다 쓴 뒤 바꿔치기해서, 중간에 멈춰도 CSV 가 깨지지 않아요. |
| 외부 접속 없음 | 이 폴더의 CSV 만 읽고 써요. 인터넷 · 다른 폴더는 건드리지 않아요. |
| 도구 표시(annotations) | 읽기 도구는 `readOnlyHint`, 쓰기 도구는 `destructiveHint=false` 로 표시해 Claude 가 위험도를 알 수 있어요. |

## 3. 데이터 (data/ 폴더)

엑셀로 열어도 한글이 안 깨지도록 **UTF-8(BOM)** 으로 저장해요. 지금 들어 있는 건 **가짜 샘플 데이터**예요. 우리 팀 데이터로 바꿔 쓰세요.

| 파일 | 칸 | 정해진 값 |
|---|---|---|
| `members.csv` | 아이디, 이름, 직군, 역할, 상태 | 아이디 = 보통 깃허브 아이디 |
| `tasks.csv` | 번호, 할 일, 직군, 담당자, 상태, 마감 | 상태: `할 일` · `진행 중` · `완료` / 마감: `YYYY-MM-DD` |
| `issues.csv` | 번호, 제목, 내용, 심각도, 상태, 담당자, 보고자, 관련 할 일, 생성일, 수정일, 메모 | 심각도: `긴급` · `높음` · `보통` · `낮음` / 상태: `열림` · `진행 중` · `해결` · `보류` |
| `worklog.csv` | 번호, 날짜, 담당자, 할 일 번호, 내용, 시간 | 시간: 0 초과 24 이하 |

> 담당자 칸은 `members.csv` 의 **아이디**와 똑같아야 해요.

## 4. 설치 · 연결

필요한 것: Python 3.10+, [uv](https://docs.astral.sh/uv/)

```powershell
cd work-remotely
uv sync            # mcp 2.x · pytest 설치 (.venv 생성)
```

**Claude Code**: 레포 맨 위 `.mcp.json` 에 이미 등록돼 있어요.
1. 레포 **맨 위 폴더**에서 `claude` 실행
2. "이 프로젝트의 MCP 서버를 쓸까요?" → **허용**
3. `/mcp` 에서 `team` 이 connected 인지 확인

**읽기 전용으로 쓰기**: `.mcp.json` 의 `env` 에 `"TEAM_READONLY": "1"` 추가

**Claude 데스크톱 앱** (`%APPDATA%\Claude\claude_desktop_config.json`, 경로는 **절대 경로**로):
```json
{
  "mcpServers": {
    "team": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\절대경로\\mcp-practice\\work-remotely", "python", "team_server.py"]
    }
  }
}
```

**uv 없이 pip 으로**: `pip install "mcp>=2"` 후 `.mcp.json` 을 `"command": "python", "args": ["work-remotely/team_server.py"]` 로 바꾸세요.

## 5. 이렇게 말해 보세요

```
team 으로 팀 대시보드 보여 줘. 일이 몰린 사람과 여유 있는 사람을 알려 줘.
team 으로 dev-jaemin 이 지금 맡은 일과 최근 한 일 보여 줘.
team 으로 긴급 · 높음 이슈만 보여 주고, 담당자 없는 이슈가 있으면 누가 맡으면 좋을지 제안해 줘.
"결제 API 타임아웃" 이슈를 높음으로 등록하려고 해. 보고자 po-seoan, 담당 dev-jaemin. 먼저 보여 줘.
team 으로 내(dev-kangi) 오늘 작업 1.5시간 기록해 줘: README 실행 방법 완성 (할 일 #1). 먼저 보여 줘.
/mcp__team__standup po-seoan
```

## 6. 오피스 화면 (office/)

team MCP 의 데이터를 사무실 도면으로 보여 주는 화면이에요. 방은 직군, 서버실의 불빛은 MCP 도구예요.

```powershell
uv run python export_office.py      # office/office.html 생성 (읽기 도구 결과를 화면에 넣음)
```

- **도면**: 팀원이 자기 직군 방 책상에 앉아 있고, 휴가인 사람은 복도 부재 칸에 있어요. 누르면 `member_status` 프로필이 열려요.
- **하루 다시 보기**: CSV 에 있는 **오늘** 작업 기록 · 이슈 등록 · 이슈 메모만 순서대로 재생해요. 이벤트마다 서버실의 해당 도구 불빛이 켜져요. 시각은 순서만 맞춘 가상 시각이에요.
- **팀 콘솔**: "누가 바빠?", "긴급 이슈", "○○ 스탠드업" 같은 질문을 어떤 team 도구로 답하는지 보여 줘요. 쓰기 요청은 실행하지 않고 Claude Code 에서 할 문장을 안내해요.
- 브라우저는 stdio MCP 서버에 직접 붙을 수 없어서 **스냅샷** 방식이에요. 데이터가 바뀌면 스크립트를 다시 실행하세요.
- `office/template.html` 이 원본, `office/office.html` 은 만들어진 결과예요.

## 7. 테스트

자세한 내용은 [TESTING.md](TESTING.md) 에 있어요. 한 줄로 돌리기:

```powershell
cd work-remotely
uv run pytest -v
node --test "tests/*.test.mjs"     # 화면 공용 함수 (office/lib.js)
```

## 8. 파일 구조

```
.mcp.json                 ← Claude Code 가 team 서버를 띄우는 설정 (레포 맨 위)
work-remotely/
├ team_server.py          ← 서버 본체 (도구 15 · 리소스 1 · 프롬프트 2)
├ export_office.py        ← 오피스 화면 만들기
├ office/                 ← template.html(원본) · office.html(결과)
├ data/                   ← CSV 4개 (가짜 샘플)
├ tests/
│ ├ conftest.py           ← 임시 폴더에 데이터 복사 · 날짜 고정
│ ├ test_tools.py         ← 도구 함수 직접 테스트 (29개)
│ └ test_mcp_protocol.py  ← 진짜 MCP 클라이언트로 연결 테스트 (6개)
├ pyproject.toml · uv.lock
├ README.md               ← 이 문서
└ TESTING.md              ← 테스트 방법 · 대화 시나리오 체크리스트
```

## 9. 알아 두면 좋은 점

- **mcp 2.x 기준**이에요. 1.x 의 `from mcp.server.fastmcp import FastMCP` 는 2.x 에서 `from mcp.server.mcpserver import MCPServer` 로 바뀌었어요.
- **도구 이름은 영어**예요. MCP 규격(SEP-986)은 도구 이름에 `A-Z a-z 0-9 _ - .` 만 허용해요. 한글은 `title` 과 설명(docstring)에 넣었어요.
- **예상한 에러는 `ToolError`** 로 던져요. 2.x 에서 일반 `ValueError` 는 "Error executing tool" 로만 보이고 메시지가 AI 에게 안 가요.
- **CSV 는 한 사람이 쓰는 걸 전제**로 해요. 팀원 여럿이 각자 PC 에서 쓰면 git 으로 합쳐야 하고, 동시에 쓰면 충돌이 나요. 여러 명이 실시간으로 같이 쓰려면 Supabase · Google Sheets 같은 공유 저장소로 옮기세요 (아래 추천 MCP 참고).

## 10. 직무별 MCP (v0.2)

직무마다 쓰는 MCP 가 달라요. `data/roles.csv` 에 직무별 **team 도구**와 **외부 MCP**를, `data/mcp_catalog.csv` 에 외부 MCP 의 프로그램 · 사이트 · 주소를 적어요.

| 직무 | 외부 MCP | team 도구 |
|---|---|---|
| 개발 | github · sentry · supabase · notion | 10개 (이슈 처리 · 마감 중심) |
| 디자인 | figma · canva · notion · slack | 9개 |
| PO | notion · linear · github · google-calendar · google-sheets · slack | 15개 전부 (팀 관리) |
| 마케팅 | canva · notion · slack · gmail · google-docs | 8개 |

- **내 직무로 켜기** (레포 맨 위에서): `claude --mcp-config work-remotely/roles/dev.mcp.json` (`design` · `po` · `mkt`)
  → team 서버는 `TEAM_ROLE` 로 그 직무 도구만 내놓고, 그 직무의 외부 MCP 만 같이 붙어요.
- `roles/*.mcp.json` 은 `export_office.py` 가 `roles.csv` 로 만들어요. 표를 고치면 다시 실행하세요.
- 구글 MCP 는 주소가 없는 claude.ai 커넥터라 파일에 안 들어가요. claude.ai › 설정 › 커넥터에서 연결하세요.
- 직무별 MCP 세트 보기: team 의 `role_toolkit` 도구 · 오피스 화면의 직무 탭

## 11. 일정 · 공수 · 기간 연장 (v0.3)

`tasks.csv` 에 **시작 · 마감 · 기준 마감(처음 정한 마감) · 예상 시간(공수)** 이 있고, 작업 기록(`worklog.csv`)의 시간이 할 일별 **실제 투입 시간**이 돼요.

| 도구 | 하는 일 | 누가 |
|---|---|---|
| `schedule_overview` | 할 일별 일정 · 공수 · 지연 · 공수 초과 · 연장 여부, 오늘까지 계획 대비 진행률 | 모두 |
| `list_extensions` | 기간 연장 신청 목록 | 모두 |
| `request_extension` | 연장 신청 (새 마감 · 사유) — 마감은 아직 안 바뀜 | 모두 |
| `review_extension` | 승인 / 반려 — 승인하면 `마감` 이 바뀌고 `기준 마감` 은 그대로 남음 | **PO 만** |

- 진행률: **완료** = 완료된 할 일의 예상 공수 ÷ 전체 예상 공수, **계획** = 각 할 일의 예상 공수 × (시작~마감 중 오늘까지 지난 비율).
- **오피스 화면**에서도 신청 · 승인할 수 있어요. 화면의 신청은 `extensions/<사람>`, PO 결정은 `decisions/<신청 키>` 에 저장되고, 승인 즉시 모든 사람의 일정표 · 마감 임박 · 지연 표시가 바뀌어요.
  - 신청: Contributor 이상 / 승인: 이 화면의 소유자 · 편집자(= PO)
- **화면 결정 → CSV 반영**: Claude Code 에서 `오피스 화면의 연장 신청 · 승인 내역을 team MCP(CSV) 에 반영해 줘` 라고 하면, 화면 데이터를 읽어 `request_extension` · `review_extension` 으로 옮기고 화면 항목에 `synced` 를 표시해요. 그 뒤 `export_office.py` 로 화면을 새로 만들어요.
- **드래그로 기간 수정** (오피스 화면 › 전체 일정 · 공수): 막대 가운데 = 일정 이동, 오른쪽 끝 = 마감, 왼쪽 끝 = 시작 (키보드: ←→ 마감, Shift+←→ 이동). 고친 건 초안으로 쌓이고, **확인 → "기간 연장 요청하시겠습니까?" → 예** 를 누르면 모두 'PO 기간 연장 승인' 탭으로 가요. PO 가 승인하면 시작 · 마감이 요청대로 바뀌어요.
- `request_extension` 은 연장뿐 아니라 단축 · 일정 이동(`new_start`)도 받아요.

## 12. 회의 (v0.4)

`data/meetings.csv` — 날짜 · 시작 · 끝 · 제목 · 참석자 · 결정 · 회의록 링크 · 기록자.

- `log_meeting` (모두, 본인 이름으로): `오늘 2시 디자인 리뷰 기록해 줘. 참석 po-seoan, design-minjeong. 결정: … 회의록: https://… 먼저 보여 줘` · 참석자에 `전원` 가능
- `list_meetings`: 최근 회의 · 내가 들어간 회의
- 오피스 화면: 라이브 피드 옆 **회의록** 패널 (회의가 없으면 공란) · 하루 다시 보기에서 회의 시간에 참석자가 회의실에 모였다가 끝나면 자리로 흩어져요.

**회의록 규칙 (v0.4.1)**: 회의록 정본은 노션 "회의록" DB (`data/settings.csv` 의 `회의록 노션 DB`). 피그마 · 깃헙은 링크로만.
`import_meetings` 명령 틀 → 상태 '완료' + 'team 기록' 빈 회의만 표로 보여 주고 "옮겨" 하면 `log_meeting` · 노션에 `회의 #번호` 표시. 같은 회의록 링크는 한 번만 기록돼요. 규칙 원문은 레포 맨 위 `CLAUDE.md`.

## 13. 재택 근무 (v0.5)

새 데이터 4개 (처음 쓸 때 만들어져요 · 지우기 없음):

| 파일 | 칸 | 정해진 값 |
|---|---|---|
| `attendance.csv` | 번호, 날짜, 아이디, 출근, 퇴근, 근무지, 메모 | 근무지: `재택` · `사무실` · `외부` / 하루 한 줄 |
| `leaves.csv` | 번호, 신청자, 종류, 시작, 끝, 사유, 상태, 검토자, 검토 메모, 신청일, 검토일 | 종류: `연차` · `반차(오전)` · `반차(오후)` · `병가` · `경조사` · `외근` / 상태: `대기` · `승인` · `반려` |
| `presence.csv` | 아이디, 상태, 메모, 바뀐 시각 | 상태: `응답 가능` · `집중` · `회의 중` · `자리 비움` / 사람마다 한 줄, 그날만 보여요 |
| `checkins.csv` | 번호, 날짜, 아이디, 어제, 오늘, 막힘 | 하루 한 번 |

| 하고 싶은 일 | 도구 | 누가 |
|---|---|---|
| 출근 · 퇴근 | `check_in` · `check_out` | 본인 |
| 지금 상태 + 한 줄 메모 | `set_status` | 본인 |
| 데일리 체크인 (어제 · 오늘 · 막힘) | `submit_checkin` (스탠드업 초안 → `저장`) | 본인 |
| 휴가 · 부재 신청 | `request_leave` | 본인 |
| 휴가 승인 · 반려 (반려는 이유 필수) | `review_leave` | **PO** |
| 오늘 근무 현황 (출퇴근 · 근무지 · 상태 · 휴가 · 체크인 · 코어 타임 · 기록 비율) | `attendance` | 모두 |
| 최근 N일 근무 시간 vs 작업 기록 → 기록 누락일 | `work_hours` | 모두 |
| 체크인 · 막힌 사람 · 미제출 | `list_checkins` | 모두 |
| 휴가 목록 (사유는 본인 · PO 만) | `list_leaves` | 모두 |
| 지금 챙길 것 + 슬랙 메시지 초안 (보내지는 않아요) | `reminders` · 프롬프트 `remote_reminder` | 모두 (보내기는 PO 가 승인 후) |

- 재택 근무 도구는 `roles.csv` 와 따로 **모든 직군**에 켜져요 (`REMOTE_TOOLS_ALL`). `review_leave` 만 PO.
- 승인된 **종일 휴가**(연차 · 병가 · 경조사)는 그날 `list_members` 의 `상태` 로 보여서 오피스 도면에서 부재 자리로 가요. 반차 · 외근은 근무로 두고 `오늘 일정` 에 적어요.
- 규칙은 `data/settings.csv` 에 행을 더하면 바뀌어요: `코어 타임` (기본 `11:00~16:00`) · `퇴근 기준` (`19:00`) · `점심 시간` (`1`, 6시간 넘게 일하면 빼요) · `기록 비율 기준` (`50`, %).
- 오피스 화면: **재택 근무** 탭 (근무 현황 표 · 체크인 · 지금 챙길 것 · 최근 7일 근무/기록 · 휴가) · 승인 탭에 **휴가 승인 대기** · 하루 다시 보기는 출퇴근 기록이 있는 날이면 그 시각에 출근 · 퇴근해요. 화면에는 휴가 **사유를 넣지 않아요**.
- 테스트용 시각 고정: `TEAM_NOW=15:00` (샘플은 2026-11-17 15:00 기준).


## 14. 팀원 추가 (관리자 화면)

오피스 화면의 **팀원 추가** 탭은 이 화면의 편집 권한이 있는 사람(관리자)에게만 보여요. **새로 들어온 사람만** 여기서 추가해요.

- 이름 · 직군 · 이메일 · (선택) 깃헙 아이디 · (선택) 배치할 프로젝트를 적으면 팀원 아이디가 `직군 키-이름 로마자` 로 제안돼요 (예: 디자인 김새봄 → `design-saebom`).
- 추가하면 **반영 대기** → 새로 고침(아래 §15) 때 `add_member` 로 CSV 에 들어가고 푸시돼요 → **CSV 반영됨** 이 되면 **보내기** 를 눌러요.
- 추가한 뒤 오피스 화면 **공유 메뉴에 그 이메일을 참여(Contributor) 권한으로** 넣어 주세요 (화면이 대신 못 해요).
- 미리보기 확인 → 관리자 **본인 Gmail** 로 설치 안내 메일이 가요 (claude.ai 의 Gmail 커넥터, 처음 한 번 허용). 메일에는 "이 메일을 받은 주소의 claude.ai 계정으로 오피스 화면을 열기" 안내와 화면 링크가 들어가요.
- 메일은 받는 사람의 이름 · 아이디가 들어간 쉬운 말 안내예요: 까만 창 열기 → uv · Claude Code 설치 → 키트 받기 (`github.com/ayla-seoan/work-remotely` 의 main.zip) → `uv run --directory work-remotely python setup_member.py <아이디>` → `claude` 에서 "team 으로 나는 누구야?". 단계 그림 6장은 화면에서 만들어 메일 본문에 넣어요 (예시 그림).
- 이메일 주소는 공개 레포 CSV 가 아니라 화면의 공유 저장소 `invites` 에 저장하고, **관리자만** 읽고 쓸 수 있어요. 보낸 시각 · 상태(보냄 · 못 보냄 · 확인 필요)도 함께 남아요.
- 응답을 못 받은 경우(확인 필요)는 Gmail 보낸편지함을 보고 필요할 때만 다시 보내요.

## 15. 프로젝트 · 공개 범위 (v0.6)

팀원은 claude.ai 계정으로 오피스 화면을 열면 **허용된 내역만** 봐요 (화면에서 가리기 — 데이터는 페이지 안에 있어요).

| 누가 | 무엇을 봐요 |
|---|---|
| 누구나 | 팀원 명단 · 근무 위치 · 상태 · 출퇴근 시각 · 근무 시간 · 휴가(사유 없이) · 프로젝트 배치 |
| 같은 프로젝트 동료 | 그 프로젝트의 할 일 · 이슈 · 작업 기록(체크인 · 회의 포함) |
| 관리자가 연 범위 | 사람(또는 전원)별로 작업 기록 · 할 일 · 이슈 |
| 관리자(화면 편집 권한) | 전부. "○○ 로 보기" 로 그 사람 화면을 미리 볼 수 있어요 |

- 데이터: `projects.csv` · `project_members.csv` · `access.csv`, 그리고 `tasks.csv` · `issues.csv` 의 `프로젝트` 칸. 계산은 `visibility.py` 한 곳.
- 도구 (쓰기는 PO 만, 먼저 보여 주고 승인): `list_projects` · `create_project` · `update_project` · `assign_member` · `end_assignment` · `add_member` · `list_access` · `grant_access` · `revoke_access`. `add_task` · `create_issue` · `list_tasks` 등에는 `project` 인자가 생겼어요.
- 화면: **프로젝트** 탭 (배치 표, 관리자는 만들기 · 배치 · 끝내기), 위쪽 **프로젝트 고르기**, 관리자 전용 **공개 범위 · 계정 연결** 패널 (이메일 같은 계정은 자동 연결, 아니면 찾아서 연결), 이메일 · 깃헙 아이디 표.
- 화면에서 관리자가 바꾼 것은 db 의 `pendingMembers` · `pendingProjects` · `pendingAccess` 에 쌓이고 **새로 고침** 때 CSV 로 옮겨져요. 계정 연결(`accounts`)만 바로 적용돼요.
- **새로 고침** (PO 의 Claude Code, `/mcp__team__sync_dashboard`): 대기열 → team 도구로 CSV → 새 팀원이 있으면 커밋 · 푸시 → `uv run python export_office.py` → 같은 주소로 다시 게시.
- 미리보기: `uv run python export_office.py 미리보기.html --as dev-kangi` (그 사람 화면만 · `full` · `public` 도 돼요).
- 게시할 때의 권한 선언 (Artifact `capabilities`, 통째로 선언하니 다시 게시할 때 이걸 그대로 써요). 대기열 · 계정 연결 · 이메일은 **관리자만** 쓰고 읽어요. 팀원은 자기 계정 연결 문서만 읽어요:

```json
{"db": {"rules": [
  {"path": "", "read": "view", "write": "admin"},
  {"path": "extensions", "read": "view", "write": "admin"}, {"path": "extensions/{self}", "read": "view", "write": "interact"},
  {"path": "events", "read": "view", "write": "admin"}, {"path": "events/{self}", "read": "view", "write": "interact"},
  {"path": "decisions", "read": "view", "write": "admin"},
  {"path": "invites", "read": "admin", "write": "admin"},
  {"path": "accounts", "read": "admin", "write": "admin"}, {"path": "accounts/{self}", "read": "view", "write": "admin"},
  {"path": "pendingMembers", "read": "admin", "write": "admin"},
  {"path": "pendingProjects", "read": "admin", "write": "admin"},
  {"path": "pendingAccess", "read": "admin", "write": "admin"}]},
 "mcp": {"servers": [{"server": "Notion", "tools": ["notion-query-data-sources", "notion-update-page", "notion-create-pages"]},
                     {"server": "Gmail", "tools": ["send_message"]}]},
 "user": {"scopes": ["profile", "email"]}}
```
- 알고 정한 한계: claude.ai 오피스 화면은 '화면에서만 가리기' 예요 (페이지 안에 데이터가 있어요). 웹(Vercel) 화면은 서버가 그 사람 몫만 보내요 (§16). 노션 '할 일 관리' 를 직접 여는 권한은 노션 공유 설정을 따라요.

## 16. 웹 화면 구글 로그인 · 저장소 나누기 (v0.7)

- **웹 화면**: https://work-remotely-kappa.vercel.app — 들어오면 "구글로 로그인" 만 보여요. 로그인 전에는 데이터가 하나도 안 와요.
  - 오피스 화면 '이메일' 칸에 적힌 구글 계정 → 그 팀원 보기 (같은 프로젝트 동료 + 관리자가 연 범위). 관리자(`ADMIN_EMAILS`) → 전체.
  - 목록에 없는 계정 → "등록되지 않은 계정이에요". 읽기 전용이에요 (입력은 claude.ai 오피스 화면).
- **구조**: `web/index.html` (데이터 없는 껍데기) + 레포 맨 위 `api/` (Node 함수: `login` · `callback` · `data` · `logout`) + `web-api/` (함수만 읽는 사람별 JSON, `accounts.json` 은 이메일 sha256 → 아이디).
- **Vercel 환경변수** (값은 Vercel 에만): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, `ADMIN_EMAILS`, `PUBLIC_URL`.
- **저장소**: 데이터 저장소 `ayla-seoan/work-remotely` 는 **비공개** (관리자만). 설치 키트는 데이터 없는 공개 저장소 `ayla-seoan/work-remotely-kit` 에서 받아요 (`make_kit.py --dir <폴더>` 로 만들어요).
- **새로 고침** (`sync_dashboard`): 대기열 반영 → 오피스 화면 `invites` 의 이메일을 `.secrets/emails.json` 으로 (git 에 안 올라가요) → `export_office.py` → 오피스 화면 다시 게시 → 데이터 저장소 커밋 · 푸시 (Vercel 자동 배포) → 명단이 바뀌었으면 키트 저장소도 푸시.
- 테스트: `uv run pytest -q` · `node --test "tests/*.test.mjs"` (함수 공용 모듈 `api/_lib.js` 포함)
