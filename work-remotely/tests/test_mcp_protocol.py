"""진짜 MCP 클라이언트로 서버에 붙어서 확인해요.

- in-process: 같은 파이썬 안에서 Client(mcp) 로 연결 (빠름)
- stdio: Claude Code 처럼 서버를 별도 프로세스로 띄워서 연결 (실제 사용과 같음)
"""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

import team_server as s

SERVER = Path(__file__).resolve().parent.parent / "team_server.py"
READ_TOOLS = {"team_dashboard", "list_members", "member_status", "list_tasks", "progress",
              "list_issues", "get_issue", "due_soon", "work_log", "role_toolkit",
              "schedule_overview", "list_extensions", "whoami", "list_meetings",
              "attendance", "work_hours", "list_checkins", "list_leaves", "reminders",
              "list_projects", "list_access"}
WRITE_TOOLS = {"create_issue", "update_issue", "add_task", "update_task_status", "log_work",
               "request_extension", "review_extension", "assign_issue", "log_meeting", "update_task",
               "check_in", "check_out", "set_status", "submit_checkin", "request_leave", "review_leave",
               "create_project", "update_project", "assign_member", "end_assignment",
               "add_member", "grant_access", "revoke_access"}


def payload(result):
    """도구 결과에서 구조화된 값(dict)을 꺼내요."""
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_in_process_tools_and_annotations(data):
    async with Client(s.mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert set(tools) == READ_TOOLS | WRITE_TOOLS
        for name in READ_TOOLS:
            assert tools[name].annotations.read_only_hint is True
        for name in WRITE_TOOLS:
            assert tools[name].annotations.destructive_hint is False
        assert tools["list_members"].description  # 설명이 있어야 AI 가 도구를 골라요


@pytest.mark.anyio
async def test_in_process_call_and_error(data):
    async with Client(s.mcp) as client:
        ok = await client.call_tool("progress", {})
        assert not ok.is_error
        assert payload(ok)["전체"] == "2/10 (20%)"

        bad = await client.call_tool("member_status", {"member_id": "nobody"})
        assert bad.is_error  # 서버가 죽지 않고 에러 결과로 돌려줘요
        assert "팀원 목록에 없어요" in bad.content[0].text


@pytest.mark.anyio
async def test_in_process_resource_and_prompt(data):
    async with Client(s.mcp) as client:
        res = await client.read_resource("team://members")
        assert "dev-kangi" in res.contents[0].text
        prompt = await client.get_prompt("standup", {"member_id": "po-seoan"})
        assert "po-seoan" in prompt.messages[0].content.text


def _stdio(data_dir, **env):
    return StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env={"TEAM_DATA_DIR": str(data_dir), "TEAM_TODAY": "2026-11-17", "PYTHONUTF8": "1", **env},
    )


@pytest.mark.anyio
async def test_stdio_end_to_end(data):
    async with Client(_stdio(data)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == READ_TOOLS | WRITE_TOOLS

        created = await client.call_tool(
            "create_issue",
            {"title": "stdio 테스트 이슈", "description": "e2e", "severity": "낮음", "reporter": "po-seoan", "project": "1"},
        )
        assert not created.is_error
        number = payload(created)["이슈"]["번호"]

        fetched = await client.call_tool("get_issue", {"issue_id": number})
        assert payload(fetched)["이슈"]["제목"] == "stdio 테스트 이슈"


@pytest.mark.anyio
async def test_mcp_json_config_starts_server(data):
    """레포 맨 위 .mcp.json 에 적힌 명령 그대로 서버를 띄워 봐요 (Claude Code 가 하는 것과 같음)."""
    repo = SERVER.parent.parent
    if not (repo / ".mcp.json").exists():
        pytest.skip("레포 맨 위 .mcp.json 이 없는 배포 키트에서는 건너뛰어요 (members/*.mcp.json 테스트가 대신 확인)")
    config = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["team"]
    params = StdioServerParameters(
        command=config["command"],
        args=config["args"],
        env={**config.get("env", {}), "TEAM_DATA_DIR": str(data), "TEAM_TODAY": "2026-11-17"},
        cwd=repo,
    )
    async with Client(params) as client:
        result = await client.call_tool("list_members", {"role": "개발"})
        assert payload(result)["팀원 수"] == 3


@pytest.mark.anyio
async def test_stdio_readonly_mode_hides_write_tools(data):
    async with Client(_stdio(data, TEAM_READONLY="1")) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == READ_TOOLS


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["개발", "design", "PO", "마케팅"])
async def test_stdio_team_role_exposes_only_that_roles_tools(data, role):
    expected = set(s.tools_for_role(role))
    async with Client(_stdio(data, TEAM_ROLE=role)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == expected


@pytest.mark.anyio
async def test_stdio_team_me_picks_role_and_identity(data):
    async with Client(_stdio(data, TEAM_ME="design-minjeong")) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == set(s.tools_for_role("디자인"))
        who = payload(await client.call_tool("whoami", {}))
        assert who["나"]["이름"] == "이민정"


@pytest.mark.anyio
async def test_member_config_starts_as_that_person(data):
    """members/<아이디>.mcp.json 명령 그대로 띄우면 '나' 가 그 사람이에요 (배포 키트의 연결 방법)."""
    cfg_path = SERVER.parent / "members" / "po-seoan.mcp.json"
    if not cfg_path.exists():
        pytest.skip("export_office.py 를 아직 안 돌려서 members/ 가 없어요")
    config = json.loads(cfg_path.read_text(encoding="utf-8"))["mcpServers"]["team"]
    params = StdioServerParameters(command=config["command"], args=config["args"],
                                   env={**config["env"], "TEAM_DATA_DIR": str(data), "TEAM_TODAY": "2026-11-17"},
                                   cwd=SERVER.parent.parent)
    async with Client(params) as client:
        who = payload(await client.call_tool("whoami", {}))
        assert who["나"]["아이디"] == "po-seoan" and who["나"]["직군"] == "PO"
