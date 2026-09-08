# -*- coding: utf-8 -*-
"""TC6: 意味重複チェック（特許ライティングマニュアル第2版 6-2）。

「約〜程度」「各〜毎」「まず初めに」等の意味重複表現を検出する。
スコープ: 明細書本文・請求項

方針: Word の文章校正（重ね言葉）に揃える。法令が用いている表現でも
重複は重複として指摘する（特許法36条5項「各請求項ごとに」等）。
そのため各パターンは漢字・ひらがなの表記違いを取りこぼさないこと。
"""

from __future__ import annotations

import re


# 固定フレーズによる意味重複
_REDUNDANT_FIXED = [
    (re.compile(r'(?:まず|先ず)(?:初め|始め|最初)に'), '「まず初めに」→「まず」または「初めに」'),
    (re.compile(r'もまた(?=[、。\s]|$)'), '「もまた」→「も」'),
    (re.compile(r'途中で中断'), '「途中で中断」→「中断」'),
    (re.compile(r'再(?:度|び)(?:繰り返|繰返|くり返)'), '「再度繰り返す」→「繰り返す」'),
    (re.compile(r'(?:予め|あらかじめ)事前[にを]'), '「予め事前に」→「事前に」'),
    (re.compile(r'互いに対向'), '「互いに対向」→「対向」'),
]

# 構造的な意味重複（距離制約あり）
_REDUNDANT_STRUCTURAL = [
    # 「約〜程度」: 約 と 程度 が近い位置に共存
    (re.compile(r'(?:約|およそ|凡そ)([^。、\n]{1,20})程度'),
     '「約〜程度」→「約〜」または「〜程度」'),
    # 「各〜毎」: 各 と 毎 が近い位置に共存
    # 「各社毎年」のように「毎」が次の語の一部となる複合語を拾わないよう、
    # 直後を助詞・句読点・行末に限定する。
    (re.compile(r'各([^。、\n]{0,10}?)毎(?=[にをはがのともでへや]|[、。\s]|$)'),
     '「各〜毎」→「各〜」または「〜毎」'),
    # 「各〜ごと」: ひらがな表記。「ごと」は複合語を作らないため直後を限定しない
    # （「各画素ごと算出する」のように助詞が省略される形も拾う）。
    # 「ごとき／ごとく」（如き）だけ除外する。
    (re.compile(r'各([^。、\n]{0,10}?)ごと(?![きく])'),
     '「各〜ごと」→「各〜」または「〜ごと」'),
]

# 数値範囲パターン（半角・全角数字、波ダッシュ・チルダ両対応）
_RANGE_PAT = re.compile(r'([０-９0-9]+)\s*[〜～]\s*([０-９0-9]+)')

def _to_half(s):
    return ''.join(chr(ord(c) - 0xFEE0) if '０' <= c <= '９' else c for c in s)

_PARA_ID_PAT = re.compile(r'【(\d{4,5})】')
_HEADING_PAT = re.compile(r'^【[^】\d][^】]*】\s*$')
_PARA_NUM_PAT = re.compile(r'【\d{4,5}】')


def check_redundant(sections):
    """TC6: 意味重複チェック。

    sections: split_sections() の戻り値
    戻り値: issue dict のリスト
    """
    issues = []
    seen = set()

    targets = [
        sections.get("description", ""),
        sections.get("claims", ""),
    ]

    all_patterns = list(_REDUNDANT_FIXED) + list(_REDUNDANT_STRUCTURAL)

    for text in targets:
        if not text:
            continue

        current_para = None
        for line in text.splitlines():
            stripped = line.strip()
            m = _PARA_ID_PAT.match(stripped)
            if m:
                current_para = 'p-' + m.group(1)

            if _HEADING_PAT.match(stripped):
                continue

            body = _PARA_NUM_PAT.sub('', stripped).strip()
            if len(body) < 4:
                continue

            for pat, note in all_patterns:
                for match in pat.finditer(body):
                    snippet = body[max(0, match.start() - 12):match.end() + 12].strip()
                    key = (note, current_para, match.group(0))
                    if key in seen:
                        continue
                    seen.add(key)
                    issue = {
                        "milestone": "TC6",
                        "level": "info",
                        "msg": f"意味が重複しています：「{match.group(0)}」— {note}",
                        "detail": snippet,
                    }
                    if current_para:
                        issue["para_id"] = current_para
                    issues.append(issue)

    # 数値範囲の桁揃えチェック（2-3: 比較対象の明示）
    # 「8〜900」のように下限の桁数が上限より2桁以上少ない場合に検出
    for text in [sections.get("description", ""), sections.get("claims", "")]:
        if not text:
            continue
        current_para = None
        for line in text.splitlines():
            stripped = line.strip()
            m = _PARA_ID_PAT.match(stripped)
            if m:
                current_para = 'p-' + m.group(1)
            if _HEADING_PAT.match(stripped):
                continue
            body = _PARA_NUM_PAT.sub('', stripped).strip()
            for match in _RANGE_PAT.finditer(body):
                lo = _to_half(match.group(1))
                hi = _to_half(match.group(2))
                if len(hi) - len(lo) >= 2:
                    snippet = body[max(0, match.start() - 10):match.end() + 10].strip()
                    key = ('range', current_para, match.group(0))
                    if key in seen:
                        continue
                    seen.add(key)
                    issue = {
                        "milestone": "TC6",
                        "level": "info",
                        "msg": (f"数値範囲の桁数に差があります：「{match.group(0)}」"
                                f"— 下限の桁数を確認してください（例: 8→800）"),
                        "detail": snippet,
                    }
                    if current_para:
                        issue["para_id"] = current_para
                    issues.append(issue)

    return issues
