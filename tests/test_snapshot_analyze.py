"""analyze() 全体のスナップショットテスト。

リファクタリング中、各 fixture に対して analyze() の出力 JSON が
変わらないことを保証する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from meisai_checker import analyze
from meisai_checker.file_reader import read_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _list_fixtures() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.txt"))


def _stable_key(obj) -> str:
    """list 内 dict の安定ソートキー。完全な JSON 化で順序を一意化。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _sort_issue_lists(issues: dict) -> dict:
    """issues 内の各リストを安定順にソートする。

    既存コード（m8_docfields._NEEDS_PARA 等）に set イテレーションがあり
    PYTHONHASHSEED 起因で順序が揺れるため、スナップショット用に正規化する。
    """
    if not isinstance(issues, dict):
        return issues
    return {k: sorted(v, key=_stable_key) if isinstance(v, list) else v
            for k, v in issues.items()}


def _normalize_for_diff(result: dict) -> dict:
    """analyze() の出力から非決定的・表示用の要素を取り除き、JSON 化する。

    `blocks` は HTML ハイライト文字列で長大かつ表示層の責務なので、
    本スナップショットでは件数のみを残す（gui.py 移動後のリグレッション検知は
    別途 GUI 動作確認で行う）。
    """
    normalized = {
        "stats": result.get("stats"),
        "claim_list": result.get("claim_list"),
        "ref_hits": result.get("ref_hits"),
        "issues": _sort_issue_lists(result.get("issues") or {}),
        "element_table": result.get("element_table"),
        "fugo_table": result.get("fugo_table"),
        "var_table": result.get("var_table"),
        "setsu_table": result.get("setsu_table"),
        "support_table": result.get("support_table"),
        "title": result.get("title"),
        "title_inv_types": result.get("title_inv_types"),
        "noun_groups": result.get("noun_groups"),
        "blocks_count": len(result.get("blocks") or []),
    }
    return normalized


def _to_json(obj) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )


@pytest.mark.parametrize(
    "fixture_path",
    _list_fixtures(),
    ids=lambda p: p.stem,
)
def test_analyze_snapshot(fixture_path: Path, update_snapshots: bool):
    if not _list_fixtures():
        pytest.skip("tests/fixtures/ にサンプル明細書がありません")

    res = read_file(str(fixture_path))
    assert "text" in res, f"file_reader 失敗: {res.get('error')}"
    text = res["text"]
    result = analyze(text)
    actual = _to_json(_normalize_for_diff(result))

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOTS_DIR / f"analyze__{fixture_path.stem}.json"

    if update_snapshots or not snapshot_path.exists():
        snapshot_path.write_text(actual, encoding="utf-8")
        if not update_snapshots:
            pytest.skip(f"baseline 作成: {snapshot_path.name}")
        return

    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"snapshot mismatch: {snapshot_path.name}\n"
        f"再生成するには: pytest --update-snapshots"
    )


def test_fixtures_present():
    """fixture が存在することを確認する。

    スナップショットテストは fixture が無ければ無意味なので、
    1 件もないときは fail させる。"""
    fixtures = _list_fixtures()
    assert fixtures, (
        "tests/fixtures/ に *.txt のサンプル明細書を 1 件以上配置してください。"
        "tests/README.md を参照。"
    )
