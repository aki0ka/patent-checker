"""個別の check_* 関数のスナップショットテスト。

analyze() 統合スナップショットが通っても個別関数の挙動差を検出できるよう、
移動対象の主要 public 関数を直接呼び出して出力を固定する。

リファクタリングの各ステップ後にも、ここが緑であることを確認する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from meisai_checker import analyzer
from meisai_checker.file_reader import read_file
from meisai_checker.parser import (
    classify_claims,
    parse_claims,
    parse_dependencies,
    split_sections,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _list_fixtures() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.txt"))


def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _build_inputs(text: str):
    """analyze() と同じやり方で sections / claims / dep_map を構築する。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    sections = split_sections(text)
    claims = parse_claims(sections.get("claims", text))
    dep_map = {
        num: [d for d in parse_dependencies(body) if d != num]
        for num, body in claims.items()
    }
    kinds = classify_claims(claims, dep_map)
    return text, sections, claims, dep_map, kinds


# (関数名, 呼び出しラムダ) のリスト。
# 呼び出しは (text, sections, claims, dep_map, kinds) を受け取り、
# JSON シリアライズ可能な戻り値を返す。
CHECK_CASES = [
    ("check_kuten",
     lambda t, sec, cl, dm, kd: analyzer.check_kuten(sec)),
    ("check_jis",
     lambda t, sec, cl, dm, kd: analyzer.check_jis({**sec, "_raw": t})),
    ("check_structure",
     lambda t, sec, cl, dm, kd: analyzer.check_structure(t)),
    ("check_para_nums",
     lambda t, sec, cl, dm, kd: analyzer.check_para_nums(t)),
    ("check_abstract",
     lambda t, sec, cl, dm, kd: analyzer.check_abstract(sec)),
    ("check_midashi_numbers",
     lambda t, sec, cl, dm, kd: analyzer.check_midashi_numbers(sec)),
    ("check_zenshou",
     lambda t, sec, cl, dm, kd: analyzer.check_zenshou(cl, dm)),
    ("check_fugo",
     # check_fugo は (issues, element_table, fugo_table, var_table) を返す
     lambda t, sec, cl, dm, kd: list(analyzer.check_fugo(cl, sec))),
    ("check_title",
     # check_title は (issues, title, title_inv_types) を返す。claim_list は省略形で十分
     lambda t, sec, cl, dm, kd: list(analyzer.check_title(
         sec,
         [{"num": n, "kind": kd[n], "is_error": False, "deps": dm.get(n, []),
           "inv_type": "", "preview": ""} for n in sorted(cl)]
     ))),
    ("check_support",
     lambda t, sec, cl, dm, kd: list(analyzer.check_support(cl, sec))),
]


@pytest.mark.parametrize(
    "fixture_path",
    _list_fixtures(),
    ids=lambda p: p.stem,
)
@pytest.mark.parametrize("func_name,caller", CHECK_CASES, ids=lambda x: x if isinstance(x, str) else "")
def test_check_func_snapshot(
    fixture_path: Path,
    func_name: str,
    caller,
    update_snapshots: bool,
):
    if not _list_fixtures():
        pytest.skip("tests/fixtures/ にサンプル明細書がありません")

    res = read_file(str(fixture_path))
    assert "text" in res, f"file_reader 失敗: {res.get('error')}"
    inputs = _build_inputs(res["text"])
    result = caller(*inputs)
    actual = _to_json(result)

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOTS_DIR / f"{func_name}__{fixture_path.stem}.json"

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
