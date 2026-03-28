# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "mcp[cli]>=1.0",
#   "fugashi>=1.3",
#   "unidic-lite>=1.0",
# ]
# ///
"""
特許明細書チェッカー MCPサーバー

起動方法:
  uv run mcp_server.py

Claude Desktop の設定例 (claude_desktop_config.json):
  {
    "mcpServers": {
      "patent-checker": {
        "command": "uv",
        "args": ["run", "/path/to/mcp_server.py"]
      }
    }
  }
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from patent_checker.analyzer import analyze
from patent_checker.preprocessor import normalize, DocFormat

mcp = FastMCP("patent-checker")

_LEVEL_ORDER = {'error': 0, 'warning': 1, 'style': 2, 'info': 3, 'ok': 4}
_MS_LABELS = {
    'm2': 'M2従属関係', 'm3': 'M3照応詞',
    'm4': 'M4符号',    'm5': 'M5誤記', 'm6': 'M6サポート',
}

def _filter_issues(issues, level):
    """レベルフィルタリング"""
    if level == 'all':
        return issues
    threshold = _LEVEL_ORDER.get(level, 4)
    return [i for i in issues if _LEVEL_ORDER.get(i.get('level', 'ok'), 4) <= threshold]

def _make_summary(result):
    """チェック結果からサマリーを生成する"""
    by_ms = {}
    total_error = total_warning = 0
    for mid in ('m2', 'm3', 'm4', 'm5', 'm6'):
        issues = result['issues'][mid]
        e = sum(1 for i in issues if i.get('level') == 'error')
        w = sum(1 for i in issues if i.get('level') == 'warning')
        by_ms[mid] = {'label': _MS_LABELS[mid], 'error': e, 'warning': w, 'total': len(issues)}
        total_error   += e
        total_warning += w
    return {
        'has_error':     total_error > 0,
        'error_count':   total_error,
        'warning_count': total_warning,
        'by_milestone':  by_ms,
        'title':         result.get('title', ''),
        'total_claims':  result['stats'].get('total_claims', 0),
    }

@mcp.tool()
def patent_check_summary(text: str, source_format: str = "auto") -> str:
    """特許明細書テキストを解析してエラー・警告のサマリーを返す。
    エラーがあるかどうかの確認、修正ループの終了判定に使用する。
    詳細なissueリストが必要な場合は patent_check_issues を使う。

    Args:
        text: 特許明細書のテキスト（【発明の名称】や【請求項N】を含む）
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        summary.has_error - エラーがあれば true
        summary.error_count / warning_count - 件数
        summary.by_milestone - マイルストーン別集計 (m2-m6)
        summary.title - 発明の名称
        summary.total_claims - 請求項数
    """
    fmt_map = {
        'jplatpat': DocFormat.JPLATPAT,
        'filing': DocFormat.FILING,
        'auto': DocFormat.UNKNOWN,
    }
    source_fmt = fmt_map.get(source_format, DocFormat.UNKNOWN)
    norm_doc = normalize(text, source_format=source_fmt)
    result = analyze(norm_doc.text)
    return json.dumps(_make_summary(result), ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_issues(text: str, level: str = "error", milestone: str = "all",
                        source_format: str = "auto") -> str:
    """特許明細書テキストを解析してissueリストを返す。

    Args:
        text: 特許明細書のテキスト
        level: "error"（エラーのみ）/ "warning"（警告以上）/ "all"（全件）
        milestone: "all" / "m2"（従属関係）/ "m3"（照応詞）/ "m4"（符号）/ "m5"（誤記）/ "m6"（サポート）
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        summary - エラー・警告サマリー
        issues - issueリスト（milestone/level/msg/detail/claim）
        claim_list - 請求項一覧（num/kind/deps/preview）
    """
    fmt_map = {
        'jplatpat': DocFormat.JPLATPAT,
        'filing': DocFormat.FILING,
        'auto': DocFormat.UNKNOWN,
    }
    source_fmt = fmt_map.get(source_format, DocFormat.UNKNOWN)
    norm_doc = normalize(text, source_format=source_fmt)
    result = analyze(norm_doc.text)
    summary = _make_summary(result)

    if milestone == 'all':
        mids = ['m2', 'm3', 'm4', 'm5', 'm6']
    elif milestone in ('m2', 'm3', 'm4', 'm5', 'm6'):
        mids = [milestone]
    else:
        return json.dumps({'error': f'不明なマイルストーン: {milestone}'}, ensure_ascii=False)

    all_issues = []
    for mid in mids:
        for iss in _filter_issues(result['issues'][mid], level):
            all_issues.append({
                'milestone': mid,
                'label':     _MS_LABELS[mid],
                'level':     iss.get('level'),
                'msg':       iss.get('msg'),
                'detail':    iss.get('detail', ''),
                'claim':     iss.get('claim'),
            })

    return json.dumps({
        'summary':    summary,
        'issues':     all_issues,
        'claim_list': [
            {'num': c['num'], 'kind': c['kind'], 'deps': c['deps'], 'preview': c['preview']}
            for c in result['claim_list']
        ],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_m3(text: str, source_format: str = "auto") -> str:
    """照応詞チェック（M3）の結果を返す。
    前記・当該の先行詞が見つからないエラーを検出する。

    Args:
        text: 特許明細書のテキスト
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        errors - 先行詞なしエラーリスト（claim/noun/word/msg）
        noun_groups - 全照応詞グループ（noun/first_claim/refs）
    """
    fmt_map = {
        'jplatpat': DocFormat.JPLATPAT,
        'filing': DocFormat.FILING,
        'auto': DocFormat.UNKNOWN,
    }
    source_fmt = fmt_map.get(source_format, DocFormat.UNKNOWN)
    norm_doc = normalize(text, source_format=source_fmt)
    result = analyze(norm_doc.text)
    errors = _filter_issues(result['issues']['m3'], 'error')
    return json.dumps({
        'errors': errors,
        'noun_groups': [
            {
                'noun':        g['noun'],
                'first_claim': g['first_claim'],
                'error':       g['error'],
                'refs': [
                    {'claim': r['claim'], 'word': r['word'], 'error': r['error']}
                    for r in g['refs']
                ],
            }
            for g in result['noun_groups']
        ],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_m4(text: str, source_format: str = "auto") -> str:
    """符号チェック（M4）の結果を返す。
    符号と要素名の対応・一貫性（多対一・一対多）を検査する。

    Args:
        text: 特許明細書のテキスト
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        errors / warnings - issueリスト
        fugo_table - 符号テーブル（fugo/names/count/is_dup）
        var_table  - 変数記号テーブル（vsym/physnames/count/is_dup）
    """
    fmt_map = {
        'jplatpat': DocFormat.JPLATPAT,
        'filing': DocFormat.FILING,
        'auto': DocFormat.UNKNOWN,
    }
    source_fmt = fmt_map.get(source_format, DocFormat.UNKNOWN)
    norm_doc = normalize(text, source_format=source_fmt)
    result = analyze(norm_doc.text)
    issues = result['issues']['m4']
    return json.dumps({
        'errors':     _filter_issues(issues, 'error'),
        'warnings':   [i for i in issues if i.get('level') == 'warning'],
        'fugo_table': result['fugo_table'],
        'var_table':  result['var_table'],
    }, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    mcp.run()
