# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "mcp[cli]>=1.0",
#   "fugashi>=1.3",
#   "unidic-lite>=1.0",
#   "pytoony>=0.1.2",
# ]
# ///
"""
特許明細書チェッカー MCPサーバー

起動方法:
  uv run mcp_server.py

Claude Desktop の設定例 (claude_desktop_config.json):
  {
    "mcpServers": {
      "meisai-checker": {
        "command": "uv",
        "args": ["run", "/path/to/mcp_server.py"]
      }
    }
  }
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pytoony import json2toon
    def _dump(obj):
        return json2toon(json.dumps(obj, ensure_ascii=False))
except ImportError:
    def _dump(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

from mcp.server.fastmcp import FastMCP
from meisai_checker.analyzer import analyze
from meisai_checker.preprocessor import normalize, DocFormat
from meisai_checker.parser import parse_claims, split_sections
from meisai_checker.patent.ambiguity import check_ambiguity
from meisai_checker.structure.docfields import check_docfields
from meisai_checker.structure.gansho import check_gansho

mcp = FastMCP("meisai-checker")

_LEVEL_ORDER = {'error': 0, 'warning': 1, 'style': 2, 'info': 3, 'ok': 4}
_MS_LABELS = {
    'm2': 'M2従属関係', 'm3': 'M3照応詞',
    'm4': 'M4符号',    'm5': 'M5誤記',  'm6': 'M6サポート',
    'm7': 'M7曖昧性',  'm8': 'M8記録項目',
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
    return _dump(_make_summary(result))


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
        return _dump({'error': f'不明なマイルストーン: {milestone}'})

    all_issues = []
    for mid in mids:
        for iss in _filter_issues(result['issues'][mid], level):
            entry = {
                'milestone': mid,
                'level':     iss.get('level'),
                'claim':     iss.get('claim'),
                'msg':       iss.get('msg'),
            }
            # 構造化データがあればそれを優先、なければ detail を付与
            if iss.get('missing_nouns'):
                entry['missing_nouns'] = iss['missing_nouns']
            elif iss.get('detail'):
                entry['detail'] = iss['detail']
            all_issues.append(entry)

    return _dump({
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
    return _dump({
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
    return _dump({
        'errors':     _filter_issues(issues, 'error'),
        'warnings':   [i for i in issues if i.get('level') == 'warning'],
        'fugo_table': result['fugo_table'],
        'var_table':  result['var_table'],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_m7(text: str, source_format: str = "auto") -> str:
    """係り受け曖昧性チェック（M7）の結果を返す。
    請求項の「前記AまたはBのC」「連用形の連続」等の曖昧パターンを検出する。
    作文支援：AIが請求項を書いたあとに呼び出し、曖昧な箇所を修正する用途に適する。

    Args:
        text: 特許明細書テキスト（請求項部分を含む）
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        issues - 曖昧性警告リスト（claim/check/level/msg）
        summary - 警告件数サマリー
    """
    fmt_map = {'jplatpat': DocFormat.JPLATPAT, 'filing': DocFormat.FILING, 'auto': DocFormat.UNKNOWN}
    norm_doc = normalize(text, source_format=fmt_map.get(source_format, DocFormat.UNKNOWN))
    sections = split_sections(norm_doc.text)
    claims = parse_claims(sections.get('claims', ''))
    issues = check_ambiguity(claims)

    by_check: dict[str, int] = {}
    for iss in issues:
        by_check[iss['check']] = by_check.get(iss['check'], 0) + 1

    return _dump({
        'summary': {
            'total':    len(issues),
            'warning':  sum(1 for i in issues if i.get('level') == 'warning'),
            'info':     sum(1 for i in issues if i.get('level') == 'info'),
            'by_check': by_check,
        },
        'issues': issues,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_m8(text: str, source_format: str = "auto") -> str:
    """記録項目チェック（M8）の結果を返す。
    特許法施行規則様式第29に基づき、明細書の記録項目の必須性・順序・
    下位構造・段落番号規則を検査する。
    作文支援：AIが明細書を生成したあとに呼び出し、書式違反を修正する用途に適する。

    Args:
        text: 特許明細書テキスト全文
        source_format: "jplatpat" / "filing" / "auto" (default: auto)

    Returns:
        issues  - 書式違反リスト（check/level/msg）
        summary - エラー・警告件数サマリー
    """
    fmt_map = {'jplatpat': DocFormat.JPLATPAT, 'filing': DocFormat.FILING, 'auto': DocFormat.UNKNOWN}
    norm_doc = normalize(text, source_format=fmt_map.get(source_format, DocFormat.UNKNOWN))
    issues = check_docfields(norm_doc.text)

    return _dump({
        'summary': {
            'total':   len(issues),
            'error':   sum(1 for i in issues if i.get('level') == 'error'),
            'warning': sum(1 for i in issues if i.get('level') == 'warning'),
        },
        'issues': issues,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def patent_check_m9(text: str) -> str:
    """特許願（願書）記録項目チェック（M9）の結果を返す。
    特許法施行規則様式第26に基づき、願書の必須項目・形式・下位構造を検査する。
    作文支援：AIが願書を生成したあとに呼び出し、記載不備を修正する用途に適する。

    対象チェック:
      GA1  必須項目の存在（書類名・あて先・発明者・特許出願人・提出物件の目録）
      GA2  【書類名】が「特許願」か
      GA3  【あて先】が「特許庁長官殿」か
      GA4  【発明者】ごとに住所・氏名があるか
      GA5  【特許出願人】の識別番号/住所/氏名の条件必須
      GA6  識別番号が9桁か
      GA7  【代理人】の識別番号・氏名の確認
      GA8  【整理番号】の形式（大文字英数字/ハイフン、10字以下）
      GA9  【国際特許分類】のIPC記号フォーマット
      GA10 【提出物件の目録】に明細書・特許請求の範囲・要約書があるか
      GA11 【手数料の表示】の支払手段と納付金額の整合性
      GA12 【持分】の形式（○／○、最大3桁/3桁）

    Args:
        text: 特許願テキスト（願書単体でも出願書類一式でも可。願書部分を自動抽出）

    Returns:
        issues  - 不備リスト（check/level/msg）
        summary - エラー・警告件数サマリー
    """
    issues = check_gansho(text)
    return _dump({
        'summary': {
            'total':   len(issues),
            'error':   sum(1 for i in issues if i.get('level') == 'error'),
            'warning': sum(1 for i in issues if i.get('level') == 'warning'),
        },
        'issues': issues,
    }, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    mcp.run()
