# -*- coding: utf-8 -*-
"""M5: 【図N】【数N】【表N】【化N】【特許文献N】等の連番チェック。

【】内の参照番号が：
  - １から始まっているか
  - 欠番・逆転なく連続しているか
  - 図のサフィックス英字（図８Ａ、図８Ｂ等）が順番（大文字小文字区別あり）に並んでいるか
"""

from __future__ import annotations

import re

# 全角数字 → 半角変換テーブル
_Z2H_DIG = str.maketrans('０１２３４５６７８９', '0123456789')
# 半角数字 → 全角変換テーブル（メッセージ表示用）
_H2Z_DIG = str.maketrans('0123456789', '０１２３４５６７８９')


def _zen2int(s: str) -> int:
    """全角または半角の数字文字列を int に変換。"""
    return int(s.translate(_Z2H_DIG))


def _int2zen(n: int) -> str:
    """int を全角数字文字列に変換（メッセージ表示用）。"""
    return str(n).translate(_H2Z_DIG)


# カテゴリ定義: (表示名, 正規表現)
# グループ1=カテゴリ名, グループ2=数字部, グループ3=英字サフィックス（図のみ）
_CATEGORIES = [
    ('図',        re.compile(r'【図([０-９0-9]+)([Ａ-Ｚａ-ｚ]*)】')),
    ('数',        re.compile(r'【数([０-９0-9]+)()】')),
    ('表',        re.compile(r'【表([０-９0-9]+)()】')),
    ('化',        re.compile(r'【化([０-９0-9]+)()】')),
    ('特許文献',  re.compile(r'【特許文献([０-９0-9]+)()】')),
    ('非特許文献', re.compile(r'【非特許文献([０-９0-9]+)()】')),
]

# サフィックスの先頭として許容する全角英字
_LETTER_START_UPPER = 'Ａ'  # FF21
_LETTER_START_LOWER = 'ａ'  # FF41


def _check_category(cat_name: str, entries: list[tuple[str, int, str]]) -> list[dict]:
    """1カテゴリ分の連番チェック。

    entries: [(raw_str, num_int, letter_suffix), ...]  ─ 出現順
    """
    issues: list[dict] = []

    # ── ベース番号の順序チェック ──────────────────────────
    # seen_nums: 重複なし・出現順のベース番号リスト
    seen_nums: list[int] = []
    num_to_letters: dict[int, list[str]] = {}

    for raw, num, letter in entries:
        if num not in num_to_letters:
            seen_nums.append(num)
            num_to_letters[num] = []
        if letter:
            num_to_letters[num].append((letter, raw))

    if not seen_nums:
        return issues

    # 1から始まるか
    if seen_nums[0] != 1:
        issues.append({
            'milestone': 'M5', 'level': 'error',
            'msg': (f'【{cat_name}】の番号が１から始まっていません'
                    f'（最初の番号: {cat_name}{_int2zen(seen_nums[0])}）'),
        })

    # 欠番・逆転チェック
    for i in range(1, len(seen_nums)):
        prev, curr = seen_nums[i - 1], seen_nums[i]
        if curr == prev:
            # 同じ番号が重複（図NＡ/図NＢ で同番号が現れる場合は正常。ここには来ない）
            pass
        elif curr != prev + 1:
            zprev, zcurr = _int2zen(prev), _int2zen(curr)
            if curr < prev:
                issues.append({
                    'milestone': 'M5', 'level': 'error',
                    'msg': (f'【{cat_name}】の番号が逆転しています'
                            f'（{cat_name}{zprev} → {cat_name}{zcurr}）'),
                })
            else:
                issues.append({
                    'milestone': 'M5', 'level': 'error',
                    'msg': (f'【{cat_name}】の番号に欠番があります'
                            f'（{cat_name}{zprev} の次が {cat_name}{zcurr}）'),
                })

    # ── 英字サフィックスのチェック（図のみ実質使用） ─────────────
    for num, letter_raw_pairs in num_to_letters.items():
        if not letter_raw_pairs:
            continue
        letters = [lr[0] for lr in letter_raw_pairs]
        raws    = [lr[1] for lr in letter_raw_pairs]

        znum = _int2zen(num)
        # 先頭はＡまたはａであるべき
        first = letters[0]
        if first != _LETTER_START_UPPER and first != _LETTER_START_LOWER:
            issues.append({
                'milestone': 'M5', 'level': 'error',
                'msg': (f'【{cat_name}{znum}】のサフィックス英字が'
                        f'「Ａ」または「ａ」から始まっていません（最初: {raws[0]}）'),
            })
            continue  # 先頭が不正なら後続順序チェックはスキップ

        # 隣接する英字が連続しているか（大文字小文字の混在も検出）
        for i in range(1, len(letters)):
            expected = chr(ord(letters[i - 1]) + 1)
            actual   = letters[i]
            if actual != expected:
                issues.append({
                    'milestone': 'M5', 'level': 'error',
                    'msg': (f'【{cat_name}{znum}】のサフィックス英字の順番が不正です'
                            f'（{raws[i - 1]} の次が {raws[i]}、'
                            f'期待値: {cat_name}{znum}{expected}）'),
                })

    return issues


def check_ref_numbers(text: str) -> list[dict]:
    """【図N】【数N】【表N】【化N】【特許文献N】【非特許文献N】の連番チェック。

    Args:
        text: 明細書全文

    Returns:
        issue リスト（milestone='M5', level='error' or 'warning'）
    """
    issues: list[dict] = []

    for cat_name, pat in _CATEGORIES:
        entries = [
            (m.group(0), _zen2int(m.group(1)), m.group(2))
            for m in pat.finditer(text)
        ]
        if entries:
            issues.extend(_check_category(cat_name, entries))

    return issues
