# -*- coding: utf-8 -*-
"""JIS X 0208 文字コードチェック。

明細書全体をスキャンし、JIS X 0208 の範囲外の文字（NEC 特殊文字、
NEC 選定 IBM 拡張、IBM 拡張、半角カタカナ等）を検出する。
代替文字の提案も含む。
"""

from __future__ import annotations


def _jis_char_status(char):
    """1文字のJIS X 0208適合状況を返す。
    戻り値: ('ok', reason) | ('ng', reason) | ('warn', reason) | ('skip', reason)
    'skip' は改ページ等の制御文字（別途処理するため個別検出対象外）
    """
    cp = ord(char)
    # 改行・タブ等の通常制御文字はスキップ（check_jis側で除外済み）
    if cp in (0x09, 0x0A, 0x0D):  # TAB, LF, CR
        return 'skip', '改行/タブ'
    # 改ページ (Form Feed): Wordからの変換で混入する可能性あり
    if cp == 0x0C:
        return 'warn', '改ページ文字（FF, U+000C）が含まれています。出願前に削除または改行に変換を推奨します。'
    # その他の制御文字 (0x00-0x1F, 0x7F)
    if cp < 0x20 or cp == 0x7F:
        return 'ng', f'制御文字（U+{cp:04X}）'

    try:
        encoded = char.encode('cp932')
    except UnicodeEncodeError:
        return 'ng', 'Shift_JIS変換不可'

    if len(encoded) == 1:
        b = encoded[0]
        if 0x20 <= b <= 0x7E:
            return 'ok', 'ASCII'
        if 0xA1 <= b <= 0xDF:
            return 'warn', '半角カタカナ（全角推奨）'
        return 'ng', f'不明な1バイト文字'

    if len(encoded) == 2:
        b1, b2 = encoded[0], encoded[1]
        # NEC特殊文字: 0x8740-0x879C（ローマ数字・丸数字・単位合字等）
        if b1 == 0x87 and 0x40 <= b2 <= 0x9C:
            return 'ng', 'NEC特殊文字（JIS X 0208外）'
        # NEC選定IBM拡張: 0xED40-0xEEFC（異体字等）
        if 0xED <= b1 <= 0xEE:
            return 'ng', 'NEC選定IBM拡張文字（JIS X 0208外）'
        # IBM拡張文字: 0xFA40-0xFC4B
        if 0xFA <= b1 <= 0xFC:
            return 'ng', 'IBM拡張文字（JIS X 0208外）'
        # 通常のShift_JIS（JIS X 0208範囲）
        return 'ok', 'JIS X 0208'

    return 'ng', '変換エラー'


# 代替文字の提案テーブル
_JIS_ALTERNATIVES = {
    'Ⅰ': 'I（半角）またはI（全角）',
    'Ⅱ': 'II（半角）またはII（全角）',
    'Ⅲ': 'III（半角）またはIII（全角）',
    'Ⅳ': 'IV（半角）またはIV（全角）',
    'Ⅴ': 'V（半角）またはV（全角）',
    'Ⅵ': 'VI（半角）',
    'Ⅶ': 'VII（半角）',
    'Ⅷ': 'VIII（半角）',
    'Ⅸ': 'IX（半角）',
    'Ⅹ': 'X（半角）',
    '①': '(1)などに変更',
    '②': '(2)などに変更',
    '③': '(3)などに変更',
    '④': '(4)などに変更',
    '⑤': '(5)などに変更',
    '⑥': '(6)などに変更',
    '⑦': '(7)などに変更',
    '⑧': '(8)などに変更',
    '⑨': '(9)などに変更',
    '⑩': '(10)などに変更',
    '㈱': '(株)に変更',
    '㌔': 'キロ またはkg等に変更',
    '㍉': 'ミリ またはmm等に変更',
    '㌃': 'アール またはa等に変更',
    '∑': 'Σ（全角Σはcp932で使用可能）',
}


def _section_label(sec_key):
    """セクションキーを日本語ラベルに変換"""
    return {
        'title': '発明の名称',
        'claims': '特許請求の範囲',
        'description': '発明の詳細な説明',
        'drawings': '図面の簡単な説明',
        'abstract': '要約',
        '_raw': '文書全体',
    }.get(sec_key, sec_key)


def check_jis(sections):
    """全セクションをスキャンしてJIS X 0208外文字を検出する。"""
    issues = []
    seen_ng   = {}  # {char: (section_label, lineno, context)}  重複排除
    seen_warn = {}

    for sec_key in ('title', 'claims', 'description', 'drawings', 'abstract', '_raw'):
        text = sections.get(sec_key, '')
        if not text:
            continue
        label = _section_label(sec_key)
        # 改ページ(\x0c)はsplitlines()で行区切りになるため事前に検出
        if '\x0c' in text:
            ff_line = next(
                (i+1 for i, l in enumerate(text.splitlines()) if '\x0c' in l), 1
            )
            context = text.splitlines()[ff_line-1].strip()[:40] if text.splitlines() else ''
            key = (sec_key, '\x0c')
            if key not in seen_warn:
                seen_warn[key] = (label, ff_line, context,
                    '改ページ文字（FF, U+000C）が含まれています。出願前に削除または改行に変換を推奨します。',
                    'U+000C')
        for lineno, line in enumerate(text.splitlines(), 1):
            for col, char in enumerate(line, 1):
                if char in (' ', '\t', '\n', '\r'):
                    continue
                status, reason = _jis_char_status(char)
                if status == 'skip':
                    continue
                if status == 'ng':
                    key = char
                    if key not in seen_ng:
                        alt = _JIS_ALTERNATIVES.get(char, '')
                        context = line.strip()[:40]
                        # 不可視文字は文字コードで表示
                        cp = ord(char)
                        display = char if cp >= 0x20 else f'U+{cp:04X}'
                        seen_ng[key] = (label, lineno, context, reason, alt, display)
                elif status == 'warn':
                    key = (sec_key, char)
                    if key not in seen_warn:
                        context = line.strip()[:40]
                        cp = ord(char)
                        display = char if cp >= 0x20 else f'U+{cp:04X}'
                        seen_warn[key] = (label, lineno, context, reason, display)

    for char, (sec_label, lineno, context, reason, alt, display) in sorted(
            seen_ng.items(), key=lambda x: ord(x[0])):
        alt_str = f'　→ {alt}' if alt else ''
        cp = ord(char)
        cp_str = f' (U+{cp:04X})' if cp < 0x20 or not char.isprintable() else ''
        issues.append({
            'milestone': 'M5',
            'level': 'warning',
            'msg': f'JIS外文字「{display}」{cp_str}が使用されています（{reason}）{alt_str}',
            'detail': f'{sec_label} 行{lineno}付近：{context}',
        })

    for (sec_key, char), (sec_label, lineno, context, reason, display) in sorted(
            seen_warn.items(), key=lambda x: x[0]):
        cp = ord(char) if len(char) == 1 else 0
        is_ctrl = (cp > 0 and cp < 0x20)
        issues.append({
            'milestone': 'M5',
            'level': 'warning' if is_ctrl else 'style',
            'msg': (f'「{display}」{reason}' if is_ctrl
                    else f'「{display}」は{reason}'),
            'detail': f'{sec_label} 行{lineno}付近：{context}',
        })

    return issues
