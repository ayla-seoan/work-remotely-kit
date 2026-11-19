"""테스트 공통 준비: tests/fixtures 의 고정 샘플을 임시 폴더에 복사해서 써요 (진짜 data/ 는 건드리지 않아요)."""

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TODAY = "2026-11-17"  # 샘플 데이터 기준 날짜로 고정 → 언제 돌려도 같은 결과
NOW = "15:00"         # 지금 시각도 고정 (출퇴근 · 알림 계산)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def data(tmp_path, monkeypatch):
    """샘플 CSV 를 임시 폴더로 복사하고, 서버가 그 폴더를 보게 해요."""
    folder = tmp_path / "data"
    shutil.copytree(ROOT / "tests" / "fixtures", folder)  # 고정된 샘플 (실제 data/ 는 노션 배치로 계속 바뀌어요)
    monkeypatch.setenv("TEAM_DATA_DIR", str(folder))
    monkeypatch.setenv("TEAM_TODAY", TODAY)
    monkeypatch.setenv("TEAM_NOW", NOW)
    return folder
