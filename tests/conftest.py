"""pytest 共通設定。

スナップショットテストの更新フラグを提供する:

    pytest --update-snapshots    # 現状の出力を golden として上書き保存
    pytest                       # golden と一致するか確認

fixture の置き場所:
    tests/fixtures/   ← gitignore。サンプル明細書を手動配置する
    tests/snapshots/  ← 追跡対象。analyze() の正解出力 (JSON)
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="現状の出力を golden snapshot として保存し直す",
    )


@pytest.fixture
def update_snapshots(request) -> bool:
    return bool(request.config.getoption("--update-snapshots"))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def snapshots_dir() -> Path:
    return SNAPSHOTS_DIR
