# -*- coding: utf-8 -*-
"""TC1: 括弧対応チェック。

全角丸括弧（）・鉤括弧「」・二重鉤括弧『』の開閉バランスを
段落・請求項単位で検査する。

スコープ: 段落【XXXX】内容・請求項本文
対象外: 【見出し】行（見出し行は括弧記法が異なるため）
"""

from __future__ import annotations

import re


# チェック対象の括弧ペア (開, 閉)
_BRACKET_PAIRS = [
    ('（', '）'),   # 全角丸括弧
    ('「', '」'),   # 鉤括弧
    ('『', '』'),   # 二重鉤括弧
]

# 段落番号行パターン
_PARA_PAT = re.compile(r'【(\d{4,5})】(.*?)(?=【\d{4,5}】|【[^０-９0-9\d]|$)', re.DOTALL)

# 請求項ブロックパターン
_CLAIM_PAT = re.compile(
    r'【請求項([０-９0-9]+)】(.*?)(?=【請求項[０-９0-9]+】|【[^０-９0-9]|$)',
    re.DOTALL)


def _check_balance(text, block_label, open_c, close_c):
    """テキスト内の open_c / close_c のバランスをチェック。
    不整合があれば issue dict を返す。
    """
    depth = 0
    first_excess_close = None
    for i, c in enumerate(text):
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth < 0 and first_excess_close is None:
                first_excess_close = i
                depth = 0  # リセットして計測継続
    if first_excess_close is not None:
        return {
            "milestone": "TC1", "level": "warning",
            "msg": f"【{block_label}】括弧「{open_c}」に対応する「{close_c}」が多すぎます",
            "detail": f"位置 {first_excess_close}：...{text[max(0,first_excess_close-5):first_excess_close+5]}...",
        }
    if depth > 0:
        return {
            "milestone": "TC1", "level": "warning",
            "msg": f"【{block_label}】括弧「{open_c}」が閉じられていません（{depth}個未閉）",
            "detail": text.strip()[-40:] if len(text.strip()) > 40 else text.strip(),
        }
    return None


def check_brackets(sections):
    """TC1: 括弧対応チェック。

    sections: split_sections() の戻り値
    戻り値: issue dict のリスト
    """
    issues = []

    # 明細書本文（段落単位）
    desc = sections.get("description", "")
    for m in _PARA_PAT.finditer(desc):
        para_id = m.group(1)
        body = m.group(2).strip()
        if not body:
            continue
        for open_c, close_c in _BRACKET_PAIRS:
            iss = _check_balance(body, para_id, open_c, close_c)
            if iss:
                iss["para_id"] = f"p-{para_id}"
                issues.append(iss)

    # 請求項
    claims_text = sections.get("claims", "")
    for m in _CLAIM_PAT.finditer(claims_text):
        claim_num = m.group(1)
        body = m.group(2).strip()
        if not body:
            continue
        for open_c, close_c in _BRACKET_PAIRS:
            iss = _check_balance(body, f"請求項{claim_num}", open_c, close_c)
            if iss:
                issues.append(iss)

    return issues
