# -*- coding: utf-8 -*-
"""TC2: 繰り返し表現チェック。

明細書・請求項中の不要な繰り返し表現を検出する:
  - 句読点の連続（。。、、）
  - 照応詞の連続（前記前記、当該当該、上記上記）
  - 助詞「の」の連続（のの）
  - 同一語の直接反復（センサセンサ、データデータ等）

スコープ: 明細書本文・請求項・要約
対象外: 見出し行【...】
"""

from __future__ import annotations

import re


# 照応詞・よく繰り返される語句
_ANAPHOR_WORDS = ['前記', '上記', '当該', '該']

# 句読点の連続パターン（全角・半角混在対応）
_PUNCT_REPEAT_PAT = re.compile(r'([。、，．]{2,}|[,\.]{2,})')

# 助詞「の」の連続
_NO_REPEAT_PAT = re.compile(r'のの+')

# 照応詞の連続
_ANAPHOR_REPEAT_PAT = re.compile(
    r'(前記|上記|当該){2,}'
)

# 段落番号行を除去して本文を取得するためのパターン
_HEADING_LINE_PAT = re.compile(r'^【[^】]+】\s*$', re.MULTILINE)
_PARA_NUM_PAT = re.compile(r'^【\d{4,5}】', re.MULTILINE)


def _iter_text_lines(text):
    """見出し行を除いたテキスト行のイテレータ。行番号(1始まり)と行テキストを返す。"""
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # 見出し行（【...】のみ）はスキップ
        if _HEADING_LINE_PAT.match(stripped):
            continue
        yield lineno, line


def check_repetition(sections):
    """TC2: 繰り返し表現チェック。

    sections: split_sections() の戻り値
    戻り値: issue dict のリスト
    """
    issues = []

    # チェック対象テキストを収集（description + claims）
    targets = [
        ("明細書", sections.get("description", "")),
        ("請求項", sections.get("claims", "")),
        ("要約",   sections.get("abstract", "")),
    ]

    for section_name, text in targets:
        if not text:
            continue
        for lineno, line in _iter_text_lines(text):
            # 段落番号部分は除外
            body = _PARA_NUM_PAT.sub('', line).strip()
            if not body:
                continue

            # ① 句読点の連続
            for m in _PUNCT_REPEAT_PAT.finditer(body):
                issues.append({
                    "milestone": "TC2", "level": "warning",
                    "msg": f"句読点が連続しています：「{m.group(0)}」（{section_name}）",
                    "detail": body[max(0, m.start()-10):m.end()+10].strip(),
                })

            # ② 「の」の連続
            for m in _NO_REPEAT_PAT.finditer(body):
                issues.append({
                    "milestone": "TC2", "level": "info",
                    "msg": f"「の」が連続しています：「{m.group(0)}」（{section_name}）",
                    "detail": body[max(0, m.start()-10):m.end()+10].strip(),
                })

            # ③ 照応詞の連続
            for m in _ANAPHOR_REPEAT_PAT.finditer(body):
                issues.append({
                    "milestone": "TC2", "level": "warning",
                    "msg": f"照応詞が連続しています：「{m.group(0)}」（{section_name}）",
                    "detail": body[max(0, m.start()-10):m.end()+10].strip(),
                })

            # ④ 同一語の直接反復（2文字以上の語が直接繰り返される）
            # 例: 「センサセンサ」「データデータ」
            # 正規表現: (.{2,8})\1（欲張りマッチで短い方から試す）
            for m in re.finditer(r'(.{2,6})\1', body):
                repeated = m.group(1)
                # 数字のみ・記号のみ・空白のみは除外
                if re.match(r'^[０-９0-9\s　]+$', repeated):
                    continue
                # 「のの」は③でカバー済み
                if repeated == 'の':
                    continue
                issues.append({
                    "milestone": "TC2", "level": "info",
                    "msg": f"語句が直接繰り返されています：「{m.group(0)}」（{section_name}）",
                    "detail": body[max(0, m.start()-5):m.end()+5].strip(),
                })

    return issues
