# team MCP 키트 — 시작하기

우리 팀의 **팀원 · 할 일 · 이슈 · 작업 기록 · 일정**을 Claude 로 함께 관리하는 MCP 서버예요.
압축을 풀고 **내 아이디로 한 번 연결**하면, Claude 가 "나" 를 알아보고 내 직무에 맞는 도구만 켜져요.

---

## 1. 누가 누구인가 (아이디 매칭)

| 이름 | 아이디 (TEAM_ME) | 직무 | team 도구 | 같이 쓰는 외부 MCP |
|---|---|---|---|---|
| 김강이 | `dev-kangi` | 개발 | 27개 | github · sentry · supabase · notion |
| 김재민 | `dev-jaemin` | 개발 | 27개 | github · sentry · supabase · notion |
| 차명근 | `dev-myeonggeun` | 개발 | 27개 | github · sentry · supabase · notion |
| 김미영 | `design-miyoung` | 디자인 | 26개 | figma · canva · notion · slack |
| 이민정 | `design-minjeong` | 디자인 | 26개 | figma · canva · notion · slack |
| 김서안 | `po-seoan` | PO | 44개 | notion · linear · github · google-calendar · google-sheets · slack |
| 신협성 | `mkt-hyeopseong` | 마케팅 | 25개 | canva · notion · slack · gmail · google-docs |

- **아이디**가 "나" 예요. 연결할 때 자기 아이디만 넣으세요.
- 작업 기록 · 이슈 등록 · 기간 변경 요청은 **내 아이디로만** 할 수 있어요 (다른 사람 이름으로 쓰면 막혀요).
- **승인 · 담당 지정은 PO 만** 할 수 있어요.
- 아이디나 직무가 틀렸으면 PO 에게 알려 주세요 (`work-remotely/data/members.csv` 를 고쳐요).

## 2. 준비물 (처음 한 번)

| 필요한 것 | 확인 | 없으면 |
|---|---|---|
| Python 3.10+ | `python --version` | https://www.python.org/downloads/ |
| uv | `uv --version` | https://docs.astral.sh/uv/getting-started/installation/ |
| Claude Code | `claude --version` | https://docs.claude.com/en/docs/claude-code |

## 3. 연결 (1분)

압축을 푼 폴더(`work-remotely-kit`)에서:

```bash
# 아이디 목록 보기
python work-remotely/setup_member.py

# 내 아이디로 연결  (Mac 은 python3)
python work-remotely/setup_member.py dev-kangi
```

스크립트가 하는 일: 아이디 확인 → `uv sync` → Claude Code 에 `team` 등록(`TEAM_ME=내 아이디`) → 내 직무의 외부 MCP 추가 명령 안내.

그다음 **아무 폴더에서** `claude` → `/mcp` 에서 `team` 이 **connected** 인지 확인 → 이렇게 물어보세요:

```
team 으로 나는 누구야?
```

> 다른 방법: 설치 없이 이번 한 번만 쓰려면 키트 폴더에서 `claude --mcp-config work-remotely/members/<내 아이디>.mcp.json`

## 4. 이렇게 말해 보세요

| 하고 싶은 것 | Claude 에게 |
|---|---|
| 내 일 보기 | `team 으로 내 할 일과 열린 이슈 보여 줘` |
| 팀 현황 | `team 으로 팀 대시보드 보여 줘. 일이 몰린 사람은?` |
| 일정 | `team 으로 일정 어때? 지연 · 공수 초과 있어?` |
| 작업 기록 | `오늘 2시간 한 거 기록해 줘: 로그인 화면 (할 일 #6, 링크 https://github.com/...) 먼저 보여 줘` |
| 이슈 등록 | `"결제 API 타임아웃" 이슈를 높음으로 등록해 줘. 먼저 보여 줘` (담당은 PO 가 지정) |
| 기간 변경 요청 | `할 일 #6 마감을 이틀 늘려 달라고 PO 에게 요청해 줘. 사유: ○○ 먼저 보여 줘` |
| 스탠드업 | `/mcp__team__standup` + 내 아이디 → 보여 주면 `저장` (오늘 체크인으로 남아요) |
| 출근 · 퇴근 | `출근 체크해 줘 (재택)` · `퇴근 체크해 줘` |
| 지금 상태 | `내 상태 '집중' 으로 바꿔 줘. 메모: 15시까지, 급하면 DM` (응답 가능 · 집중 · 회의 중 · 자리 비움) |
| 휴가 · 부재 | `11/28 연차 신청해 줘` · `내일 오후 반차 신청해 줘` (PO 가 승인하면 근무 현황에 반영) |
| 근무 현황 | `지금 누가 일해? 김재민 지금 말 걸어도 돼?` · `이번 주 내 근무 시간이랑 기록 빠진 날` |
| **PO 만** | `승인 대기 중인 기간 변경 보여 주고 #2 승인해 줘` · `담당 없는 이슈 #3 을 mkt-hyeopseong 에게 맡겨 줘` · `휴가 신청 #3 승인해 줘` · `/mcp__team__remote_reminder` (슬랙 알림 초안 → 승인 후 보내기) |

## 5. 회의록 규칙

> **회의록은 노션 "회의록" 데이터베이스 한 곳에 쓴다. 피그마 · 깃헙 자료는 그 안에 링크로 붙인다.**
> 노션 회의록 DB: https://app.notion.com/p/41bb77b7c99a81ce8a88d05995cb0d6e (D25 MCP 실습 아래)

| 노션 칸 | 쓰는 법 |
|---|---|
| 회의 | 제목 (예: 데일리 스탠드업) |
| 날짜 | 날짜 + **시작~끝 시간** (예: 11/17 14:00 → 14:40) |
| 참석자 · 기록자 | 목록에서 `이름 · 아이디` 고르기 |
| 결정 | 결정 사항 한두 줄 |
| 자료 링크 | 피그마 · 깃헙 등 회의 자료 |
| 상태 | 다 쓰면 **완료** 로 |
| team 기록 | 비워 두기 (Claude 가 옮긴 뒤 `회의 #번호` 를 채워요) |

회의가 끝나면 기록자가 Claude Code 에서 `/mcp__team__import_meetings` → 표 확인 → "옮겨".
그러면 오피스 화면의 **회의록** 칸과 **하루 다시 보기**(회의실에 모였다 흩어지기)에 나와요.

## 6. 대시보드 (팀 오피스)

PO 가 공유한 **팀 오피스** 링크(claude.ai, 조직 안에서만 열려요)에서:
- **팀 오피스** — 도면 · 이슈 보드 · 라이브 피드 · 히스토리
- **전체 일정 · 공수** — 막대를 드래그해 기간을 고치고 **확인 → "기간 연장 요청하시겠습니까?" → 예** 로 PO 에게 요청
- **PO 승인 · 지정** — PO 가 승인 · 반려 · 담당 지정 (모두의 화면이 바로 바뀌어요)

## 7. 꼭 알아 두세요 — 데이터는 어디에 있나

- 이 키트의 `work-remotely/data/*.csv` 는 **내 컴퓨터에 있는 복사본**이에요. 내가 기록한 건 **다른 사람 컴퓨터에 자동으로 가지 않아요.**
- 팀이 같은 데이터를 보려면 **공유 저장소(비공개 GitHub 레포)** 로 맞춰요:
  1. 일 시작 전 `git pull`
  2. Claude 로 기록 · 요청한 뒤 `git add work-remotely/data && git commit -m "작업 기록" && git push`
  3. 같은 줄을 동시에 고쳐 충돌이 나면 PO 에게 알려 주세요
- 대시보드의 **기간 변경 요청 · 승인 · 담당 지정**은 화면에서 실시간으로 공유돼요. CSV 에 옮기는 건 PO 가 Claude 로 해요.
- 토큰(`GITHUB_PAT` 등)은 **각자 환경변수**에만. 레포 · 슬랙 · 화면 공유에 ❌

## 8. 안전장치

- 지우기 도구가 없어요 — 이슈는 '해결', 할 일은 '완료'로.
- 잘못된 아이디 · 날짜 · 상태는 저장하지 않고 고칠 방법을 알려 줘요.
- 처음 써 볼 땐 읽기 전용으로: 등록 명령에 `-e TEAM_READONLY=1` 추가.

## 9. 막히면

| 증상 | 해결 |
|---|---|
| `/mcp` 에 team 이 없음 | `python work-remotely/setup_member.py <아이디>` 다시 실행 → claude 껐다 켜기 |
| team ✘ failed | 키트 폴더에서 `cd work-remotely && uv sync` → `uv run python team_server.py` 로 에러 확인 (멈춰 있으면 정상, Ctrl+C) |
| "나는 누구야?" 가 None | 등록에 `TEAM_ME` 가 빠짐 → setup 다시 실행 |
| "다른 사람 이름으로는 할 수 없어요" | 정상이에요. 내 아이디로만 기록 · 요청할 수 있어요 |
| 한글 깨짐 | CSV 는 UTF-8 로 저장 (엑셀은 "CSV UTF-8") |
| 연결 끊기 | `claude mcp remove team --scope user` |
