# -*- coding: utf-8 -*-
"""発明の名称チェック (M5)。

発明の名称と独立請求項の発明種類の整合、および請求項内の句点の有無をチェックする。
"""

from __future__ import annotations

import re

from ..parser import KIND_INDEPENDENT, z2h


def check_title(sections, claim_list):
    """発明の名称チェック"""
    issues = []
    title_section = sections.get("title", "")
    m = re.search(r'【発明の名称】\s*(.+)', title_section)
    title = m.group(1).strip() if m else ""

    # 独立請求項の末尾体言を収集
    inv_types = list(dict.fromkeys(
        c["inv_type"] for c in claim_list
        if c["kind"] == KIND_INDEPENDENT and c["inv_type"] != "不明"
    ))

    # 句点忘れ検出: 各請求項で「。」の前に「【」がある場合
    claims_text = sections.get("claims", "")
    for mm in re.finditer(r'【請求項([０-９0-9]+)】(.*?)(?=【請求項[０-９0-9]+】|【[^０-９0-9]|$)',
                           claims_text, re.DOTALL):
        num  = int(z2h(mm.group(1)))
        body = mm.group(2)
        kuten_pos = body.find('。')
        bracket_pos = body.rfind('【')
        # 「。」がない、または「【」が「。」より後にある
        if kuten_pos < 0:
            issues.append({
                "milestone": "M5", "level": "warning",
                "msg": f"請求項{num}：句点「。」が見つかりません（句点忘れの可能性）",
                "detail": f"末尾: {body.strip()[-30:]}"
            })
        elif bracket_pos > kuten_pos:
            issues.append({
                "milestone": "M5", "level": "warning",
                "msg": f"請求項{num}：句点「。」の後に「【」があります（句点忘れの可能性）",
                "detail": f"「。」位置: {kuten_pos}、「【」位置: {bracket_pos}"
            })

    if not title:
        issues.append({
            "milestone": "M5", "level": "error",
            "msg": "発明の名称が見つかりません"
        })
        return issues, title, inv_types

    # 独立請求項の発明種類が全て名称に含まれているか
    missing = [t for t in inv_types if t not in title]
    if missing:
        issues.append({
            "milestone": "M5", "level": "warning",
            "msg": (f"発明の名称「{title}」に含まれない独立請求項の発明種類があります：" +
                    "、".join(missing)),
            "detail": f"独立請求項の発明種類：{' / '.join(inv_types)}"
        })
    else:
        issues.append({
            "milestone": "M5", "level": "ok",
            "msg": f"発明の名称「{title}」は独立請求項の発明種類をすべて含んでいます",
            "detail": f"発明種類：{' / '.join(inv_types)}"
        })

    return issues, title, inv_types
