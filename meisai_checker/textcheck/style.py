# -*- coding: utf-8 -*-
"""TC3: 文体チェック（常体/敬体の整合性）。

特許明細書は常体（〜する。〜である。）で記述するのが原則。
敬体（〜です。〜ます。〜でした。〜ください。）が混入している箇所を検出する。

スコープ: 明細書本文（description）・請求項（claims）
対象外: 要約書（要約書は敬体が使われることがある）・見出し行
"""

from __future__ import annotations

import re


# 敬体の末尾パターン（文末 or 読点の直前まで）
# 「〜です」「〜ます」「〜でした」「〜ました」「〜ください」「〜ましょう」
# 「〜であります」「〜おります」「〜います」「〜おりません」「〜できません」
_KEITAL_SENTENCE_PAT = re.compile(
    r'(?:'
    r'[^。\n]{2,}'     # 文頭から2文字以上
    r'(?:'
    r'です'
    r'|ます'
    r'|でした'
    r'|ました'
    r'|ません'
    r'|でしょう'
    r'|ましょう'
    r'|ください'
    r'|なさい'
    r'|であります'
    r'|おります'
    r'|います'
    r'|おりません'
    r'|できます'
    r'|あります'
    r')'
    r')(?:。|、|$|\n)'
)

# 明らかに常体の文脈で許容される「あります」（「問題があります。」→NG、「記載があります」→NG）
# 判定が難しいため、全てを一律で検出して人間が判断するレベルに留める

# 見出し行・段落番号行のパターン
_HEADING_PAT = re.compile(r'^【[^】]+】\s*$')
_PARA_NUM_PAT = re.compile(r'^【\d{4,5}】')


def check_style(sections):
    """TC3: 文体チェック（敬体の混入を検出）。

    sections: split_sections() の戻り値
    戻り値: issue dict のリスト
    """
    issues = []

    # チェック対象: 明細書本文・請求項
    # 要約書は対象外（敬体が許容されることがある）
    targets = [
        ("明細書", sections.get("description", "")),
        ("請求項", sections.get("claims", "")),
    ]

    seen = set()  # 重複メッセージ抑制

    for section_name, text in targets:
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # 見出し行・段落番号行はスキップ
            if _HEADING_PAT.match(stripped):
                continue
            # 段落番号部分を除去
            body = _PARA_NUM_PAT.sub('', stripped).strip()
            if len(body) < 4:
                continue

            for m in _KEITAL_SENTENCE_PAT.finditer(body):
                snippet = m.group(0).strip()[:40]
                key = (section_name, snippet)
                if key in seen:
                    continue
                seen.add(key)
                issues.append({
                    "milestone": "TC3", "level": "warning",
                    "msg": f"敬体（です・ます体）が使用されています（{section_name}）："
                           f"「{snippet}」",
                    "detail": f"明細書は常体（〜する。〜である。）で記述することが原則です",
                })

    return issues
