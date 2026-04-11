# -*- coding: utf-8 -*-
"""要約書チェック。

特許法施行規則第25条の2に基づく要約書の文字数 (400 字以内) と
必須項目 (【課題】【解決手段】) の存在をチェックする。
"""

from __future__ import annotations

import re


def check_abstract(sections):
    """要約の文字数・必須項目をチェック。"""
    issues = []
    ab = sections.get('abstract', '')
    if not ab:
        issues.append({
            'milestone': 'M5', 'level': 'info',
            'msg': '【要約】セクションが見つかりません',
        })
        return issues

    # 段落番号・見出し行・(57)プレフィックス等を除いた本文文字数
    text_only = re.sub(r'【[^】]+】', '', ab)          # 見出し除去
    text_only = re.sub(r'^\s*\(\d+\)', '', text_only)   # (57)等除去
    text_only = re.sub(r'\s', '', text_only)             # 空白除去
    char_count = len(text_only)

    if char_count > 400:
        issues.append({
            'milestone': 'M5', 'level': 'warning',
            'msg': f'要約が400字を超えています（{char_count}字）',
            'detail': '特許法施行規則第25条の2：要約書は400字以内',
        })
    else:
        issues.append({
            'milestone': 'M5', 'level': 'ok',
            'msg': f'要約文字数：{char_count}字（400字以内）',
        })

    # 必須項目チェック：【課題】【解決手段】
    for item in ('【課題】', '【解決手段】'):
        if item not in ab:
            issues.append({
                'milestone': 'M5', 'level': 'warning',
                'msg': f'要約に{item}がありません',
                'detail': '要約書の記載項目：【課題】【解決手段】',
            })

    return issues
