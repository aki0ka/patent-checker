# -*- coding: utf-8 -*-
"""
特許明細書チェッカー - CLI モジュール

コマンドラインインターフェイス、ファイル解析、出力フォーマット制御を担当。
"""

import argparse
import json as _json
import sys as _sys
import tempfile
import atexit
import webbrowser
import html as _html_module
import os

from .analyzer import analyze, build_blocks
from .parser import from_bytes
from .preprocessor import DocFormat, normalize


# ══════════════════════════════════════════════════════════
# ヘルパー関数
# ══════════════════════════════════════════════════════════

_LEVEL_ORDER = {'error': 0, 'warning': 1, 'style': 2, 'info': 3, 'ok': 4}
_LEVEL_MARK = {'error': '❌', 'warning': '⚠️ ', 'style': '📝', 'info': 'ℹ️ ', 'ok': '✅'}
_MS_LABEL = {
    'm2': 'M2 従属関係', 'm3': 'M3 照応詞',
    'm4': 'M4 符号',    'm5': 'M5 誤記',  'm6': 'M6 サポート',
}


def _make_summary(result):
    """チェック結果からサマリーを生成する"""
    by_ms = {}
    total_error = total_warning = 0
    for mid in ('m2', 'm3', 'm4', 'm5', 'm6'):
        issues = result['issues'][mid]
        e = sum(1 for i in issues if i.get('level') == 'error')
        w = sum(1 for i in issues if i.get('level') == 'warning')
        by_ms[mid] = {'error': e, 'warning': w, 'total': len(issues)}
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


def _filter_issues(issues, level_filter):
    """レベルフィルタリング"""
    if level_filter == 'all':
        return issues
    threshold = _LEVEL_ORDER.get(level_filter, 4)
    return [i for i in issues if _LEVEL_ORDER.get(i.get('level', 'ok'), 4) <= threshold]


def _generate_html_report(result):
    """HTML形式のレポートを生成する"""
    summary = _make_summary(result)

    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append('<html lang="ja">')
    html_parts.append("<head>")
    html_parts.append('<meta charset="utf-8">')
    html_parts.append("<title>特許明細書チェッカー - レポート</title>")
    html_parts.append("<style>")
    html_parts.append("""
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        h2 { color: #666; border-bottom: 2px solid #ddd; padding-bottom: 5px; }
        .summary { background: white; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .error { color: #d32f2f; font-weight: bold; }
        .warning { color: #f57c00; font-weight: bold; }
        .ok { color: #388e3c; }
        table { width: 100%; border-collapse: collapse; background: white; margin: 15px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f5f5f5; font-weight: bold; }
        .section { background: white; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .issue { padding: 10px; margin: 10px 0; border-left: 4px solid #ddd; }
        .issue.error { border-left-color: #d32f2f; }
        .issue.warning { border-left-color: #f57c00; }
        .detail { color: #666; font-size: 0.9em; margin-top: 5px; }
    """)
    html_parts.append("</style>")
    html_parts.append("</head>")
    html_parts.append("<body>")

    # タイトルとサマリー
    title = result.get('title', '（タイトル不明）')
    html_parts.append(f"<h1>特許明細書チェッカー - {_html_module.escape(title)}</h1>")

    html_parts.append('<div class="summary">')
    html_parts.append(f"<p><strong>請求項数:</strong> {summary['total_claims']}</p>")

    if not summary['has_error']:
        html_parts.append('<p class="ok">✅ エラーなし</p>')
    else:
        html_parts.append(f'<p><span class="error">❌ エラー {summary["error_count"]}件</span> '
                          f'<span class="warning">⚠️ 警告 {summary["warning_count"]}件</span></p>')

    html_parts.append("<table><tr><th>マイルストーン</th><th>エラー</th><th>警告</th></tr>")
    for mid, ms in summary['by_milestone'].items():
        label = _MS_LABEL.get(mid, mid)
        html_parts.append(f"<tr><td>{_html_module.escape(label)}</td>"
                          f"<td>{ms['error']}</td><td>{ms['warning']}</td></tr>")
    html_parts.append("</table>")
    html_parts.append("</div>")

    # 統計
    html_parts.append('<div class="section">')
    html_parts.append("<h2>統計</h2>")
    s = result['stats']
    html_parts.append("<table><tr><th>項目</th><th>値</th></tr>")
    html_parts.append(f"<tr><td>文字数</td><td>{s.get('total_chars', 0)}</td></tr>")
    html_parts.append(f"<tr><td>段落数</td><td>{s.get('total_paras', 0)}</td></tr>")
    html_parts.append(f"<tr><td>請求項数</td><td>{s.get('total_claims', 0)}</td></tr>")
    html_parts.append(f"<tr><td>推定ページ数</td><td>{s.get('total_pages', 0)}</td></tr>")
    html_parts.append("</table>")
    html_parts.append("</div>")

    # Issues（マイルストーン別）
    for mid, mlabel in _MS_LABEL.items():
        issues = result['issues'][mid]
        if not issues:
            continue

        html_parts.append('<div class="section">')
        html_parts.append(f"<h2>{_html_module.escape(mlabel)} ({len(issues)}件)</h2>")

        for iss in issues:
            level = iss.get('level', '?')
            mark = _LEVEL_MARK.get(level, '  ')
            msg = _html_module.escape(iss.get('msg', ''))
            detail = iss.get('detail', '')
            claim = iss.get('claim', '')

            html_parts.append(f'<div class="issue {level}">')
            html_parts.append(f"<p>{mark} <strong>{msg}</strong></p>")
            if claim:
                html_parts.append(f"<p><strong>請求項:</strong> {claim}</p>")
            if detail:
                html_parts.append(f'<div class="detail">{_html_module.escape(detail)}</div>')
            html_parts.append("</div>")

        html_parts.append("</div>")

    html_parts.append("</body>")
    html_parts.append("</html>")

    return "\n".join(html_parts)


# ══════════════════════════════════════════════════════════
# メイン CLI 関数
# ══════════════════════════════════════════════════════════

def main():
    """CLI メインエントリポイント"""
    parser = argparse.ArgumentParser(
        prog='patent_checker',
        description='特許明細書方式チェッカー',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  ファイル解析（サマリー表示）:
    python -m patent_checker.cli -f 明細書.txt

  詳細出力（全issues）:
    python -m patent_checker.cli -f 明細書.txt -v

  エラーのみ表示:
    python -m patent_checker.cli -f 明細書.txt --level error

  JSON出力（LLM・エージェント連携用）:
    python -m patent_checker.cli -f 明細書.txt --json
    python -m patent_checker.cli -f 明細書.txt --json --level error
    python -m patent_checker.cli -f 明細書.txt --json --section m3

  テキスト直接入力:
    python -m patent_checker.cli -t "【発明の名称】..."

  HTML形式レポート生成（ブラウザで表示）:
    python -m patent_checker.cli -f 明細書.txt --html
        """,
    )

    parser.add_argument('-f', '--file',  metavar='FILE', help='解析する明細書テキストファイル')
    parser.add_argument('-t', '--text',  metavar='TEXT', help='解析するテキスト（直接入力）')
    parser.add_argument('-v', '--verbose', action='store_true', help='詳細出力（全issues）')
    parser.add_argument('--json', action='store_true', help='JSON形式で出力（LLM連携用）')
    parser.add_argument('--html', action='store_true', help='HTML形式レポートを生成してブラウザで表示')
    parser.add_argument('--format', metavar='FMT',
                        choices=['jplatpat', 'filing', 'auto'],
                        default='auto',
                        help='入力フォーマット: jplatpat / filing / auto (default: auto)')
    parser.add_argument('--level', metavar='LVL',
                        choices=['error', 'warning', 'all'],
                        default='all',
                        help='表示するissueのレベル: error / warning / all (default: all)')
    parser.add_argument('--section', metavar='SEC',
                        choices=['all', 'stats', 'claims', 'm2', 'm3', 'm4', 'm5', 'm6',
                                 'fugo', 'var', 'support'],
                        default='all', help='出力するセクション (default: all)')

    args = parser.parse_args()

    # 入出力モード判定
    if args.file or args.text:
        # ファイル or テキスト入力モード
        if args.file:
            with open(args.file, 'rb') as fh:
                raw_text = from_bytes(fh.read())
        else:
            raw_text = args.text

        # フォーマット変換
        fmt_map = {
            'jplatpat': DocFormat.JPLATPAT,
            'filing': DocFormat.FILING,
            'auto': DocFormat.UNKNOWN,
        }
        source_fmt = fmt_map.get(args.format, DocFormat.UNKNOWN)
        norm_doc = normalize(raw_text, source_format=source_fmt)

        # 解析実行
        result = analyze(norm_doc.text)
        summary = _make_summary(result)
        sec = args.section
        lvl = args.level

        # HTML出力
        if args.html:
            html_content = _generate_html_report(result)

            # 一時ファイルに書き込み
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                            encoding='utf-8') as f:
                f.write(html_content)
                temp_path = f.name

            # ブラウザで開く
            file_url = 'file:///' + temp_path.replace('\\', '/').lstrip('/')
            webbrowser.open(file_url)

            # 終了時に一時ファイルを削除
            atexit.register(lambda: os.path.exists(temp_path) and os.unlink(temp_path))

            print(f"HTMLレポートをブラウザで表示しました: {temp_path}")
            _sys.exit(0)

        # JSON出力
        if args.json:
            out = {'summary': summary}
            if sec in ('all', 'stats'):
                out['stats'] = result['stats']
            if sec in ('all', 'claims'):
                out['claims'] = result['claim_list']
            if sec in ('all', 'm2'):
                out['m2_issues'] = _filter_issues(result['issues']['m2'], lvl)
            if sec in ('all', 'm3'):
                out['m3_issues'] = _filter_issues(result['issues']['m3'], lvl)
                out['noun_groups'] = result['noun_groups']
            if sec in ('all', 'm4', 'fugo'):
                out['m4_issues'] = _filter_issues(result['issues']['m4'], lvl)
                out['fugo_table'] = result['fugo_table']
            if sec in ('all', 'var'):
                out['var_table'] = result['var_table']
            if sec in ('all', 'm5'):
                out['m5_issues'] = _filter_issues(result['issues']['m5'], lvl)
                out['title'] = result['title']
            if sec in ('all', 'm6', 'support'):
                out['m6_issues'] = _filter_issues(result['issues']['m6'], lvl)
                out['support_table'] = result['support_table']

            print(_json.dumps(out, ensure_ascii=False, indent=2))

        # テキスト出力
        else:
            # サマリー（--section all のとき先頭に表示）
            if sec == 'all':
                title = result.get('title') or '（タイトル不明）'
                print(f"【特許明細書チェッカー】{title}  請求項数: {summary['total_claims']}")
                print()
                if not summary['has_error']:
                    print("  ✅ エラーなし")
                else:
                    print(f"  ❌ エラー {summary['error_count']}件  "
                          f"⚠️  警告 {summary['warning_count']}件")
                for mid, ml in _MS_LABEL.items():
                    ms = summary['by_milestone'][mid]
                    parts = []
                    if ms['error']:   parts.append(f"error:{ms['error']}")
                    if ms['warning']: parts.append(f"warning:{ms['warning']}")
                    tag = ' / '.join(parts) if parts else 'OK'
                    print(f"    {ml}: {tag}")
                print()

            # 統計
            if sec in ('all', 'stats'):
                s = result['stats']
                print(f"=== 統計 ===")
                print(f"  文字数: {s.get('total_chars', 0)}")
                print(f"  段落数: {s.get('total_paras', 0)}")
                print(f"  請求項数: {s.get('total_claims', 0)}")
                print(f"    独立: {s.get('独立', 0)}  単項従属: {s.get('単項従属', 0)}"
                      f"  マルチ: {s.get('マルチクレーム', 0)}")
                print(f"  推定ページ数: {s.get('total_pages', 0)}")

            # 請求項一覧
            if sec in ('all', 'claims'):
                print(f"\n=== 請求項一覧 ===")
                for c in result['claim_list']:
                    kind_str = '独立' if c['kind'] == '独立' else f"{c['kind']}({','.join(map(str, c['deps']))})"
                    err_mark = ' ⚠️' if c['is_error'] else ''
                    print(f"  請求項{c['num']:3d} [{kind_str:16s}]{err_mark} {c['inv_type']} | {c['preview'][:40]}")

            # Issues（マイルストーン別）
            for mid, mlabel in _MS_LABEL.items():
                ms_secs = {'fugo': 'm4', 'var': 'm4', 'support': 'm6'}
                if sec not in ('all', mid) and ms_secs.get(sec) != mid:
                    continue

                misissues_raw = result['issues'][mid]
                misissues = _filter_issues(misissues_raw, lvl)
                if not args.verbose:
                    misissues = _filter_issues(misissues, 'warning')
                if not misissues:
                    if args.verbose:
                        print(f"\n=== {mlabel} ✅ 問題なし ===")
                    continue

                print(f"\n=== {mlabel} ({len(misissues)}件) ===")
                for iss in misissues:
                    lvl_val = iss.get('level', '?')
                    mark = _LEVEL_MARK.get(lvl_val, '  ')
                    print(f"  {mark} {iss.get('msg', '')}")
                    if args.verbose and iss.get('detail'):
                        print(f"      {iss['detail']}")

            # 符号テーブル（-v のとき）
            if sec in ('all', 'fugo', 'm4') and args.verbose:
                print(f"\n=== 符号付き要素 ({len(result['fugo_table'])}件) ===")
                for row in result['fugo_table']:
                    dup = '⚠️ ' if row['is_dup'] else '   '
                    print(f"  {dup}{row['fugo']:8s} → {' / '.join(row['names'])} ({row['count']}回)")

            # 変数記号テーブル（-v のとき）
            if sec in ('all', 'var', 'm4') and args.verbose:
                print(f"\n=== 変数記号 ({len(result['var_table'])}件) ===")
                for row in result['var_table']:
                    dup = '⚠️ ' if row['is_dup'] else '   '
                    print(f"  {dup}{row['vsym']:8s} → {' / '.join(row['physnames'])} ({row['count']}回)")

            # サポートテーブル（-v のとき）
            if sec in ('all', 'support', 'm6') and args.verbose:
                print(f"\n=== サポート要件 ({len(result['support_table'])}件) ===")
                for row in result['support_table']:
                    flags = ('解決手段:' + ('✓' if row['in_solve'] else '✗') + ' ' +
                             '実施形態:' + ('✓' if row['in_impl'] else '✗') + ' ' +
                             '詳細説明:' + ('✓' if row['in_desc'] else '✗'))
                    claims_str = ','.join(map(str, row['claims']))
                    print(f"  請求項{claims_str:8s} {row['noun']:20s} {flags}")

        _sys.exit(0)
    else:
        # ファイルもテキストも指定されていない
        parser.print_help()
        _sys.exit(1)


if __name__ == '__main__':
    main()
