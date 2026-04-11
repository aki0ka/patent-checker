# -*- coding: utf-8 -*-
"""G1: 助詞の連続チェック（Layer 5 — MeCab必須）

検出パターン:
  G1a: 同一助詞の直接連続（「のの」「ながなが」等 — ほぼ誤り）
  G1b: 「の」の過剰連鎖（4連以上 — 「AのBのCのDのE」）

スコープ: 請求項・明細書本文。要約書は対象外。
"""

from __future__ import annotations

import re

# 助詞「の」のみで構成される連鎖を数えるため、
# 連続する「名詞系 の 名詞系 の ...」を追跡する。
_NO_CHAIN_MIN = 4  # この数以上の「の」連鎖で G1b を発報

# G1a で無視する助詞（正常な連続が存在するもの）
# 例: 「においては」→ に + おい + て + は　（MeCab が分割する）
# 例: 「たり〜たり」→ 同一助詞（並立助詞）の連続は文法的に正常
_G1A_IGNORE_SURF = {
    'たり',  # 〜たり〜たり（並立）
    'か',    # 〜か〜か（選択）
    'も',    # 〜も〜も（並立）
    'や',    # 〜や〜や（並立）
}


def _extract_sections_text(sections: dict) -> list[tuple[str, str]]:
    """チェック対象セクションを (セクション名, テキスト) のリストで返す。"""
    result = []
    for key, label in [("claims", "請求項"), ("description", "明細書")]:
        text = sections.get(key, "")
        if text:
            result.append((label, text))
    return result


def _get_context(text: str, start: int, end: int, window: int = 20) -> str:
    """位置 start〜end の前後 window 文字を抜粋して返す。"""
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return f"…{snippet}…" if lo > 0 or hi < len(text) else snippet


def check_particles(sections: dict) -> list[dict]:
    """G1: 助詞の連続チェック。

    sections: split_sections() の戻り値
    戻り値: issue dict のリスト
    """
    try:
        from ..tokenizer import _tokenize
    except Exception:
        return []

    issues: list[dict] = []
    seen: set[tuple] = set()  # 重複抑制

    for section_label, text in _extract_sections_text(sections):
        tokens = _tokenize(text)
        n = len(tokens)

        i = 0
        while i < n:
            tok = tokens[i]

            # ── G1a: 同一助詞の直接連続 ──────────────────────────
            if tok["pos"] == "助詞" and tok["surf"] not in _G1A_IGNORE_SURF:
                if i + 1 < n:
                    nxt = tokens[i + 1]
                    if (nxt["pos"] == "助詞"
                            and nxt["surf"] == tok["surf"]
                            and tok["surf"] not in _G1A_IGNORE_SURF):
                        surf = tok["surf"]
                        pos = tok["start"]
                        key = ("G1a", section_label, surf, pos)
                        if key not in seen:
                            seen.add(key)
                            ctx = _get_context(text, pos, nxt["end"])
                            issues.append({
                                "milestone": "G1", "level": "warning",
                                "msg": (f"助詞「{surf}」が連続しています"
                                        f"（{section_label}）：「{ctx}」"),
                                "detail": "同一助詞の直接連続は誤記の可能性があります。",
                            })

            # ── G1b: 「の」の過剰連鎖 ────────────────────────────
            # トークン列で「名詞系 の 名詞系 の ...」の長さを計測
            if tok["pos"] == "助詞" and tok["surf"] == "の":
                # 現在位置から後ろ向きに「の」の連鎖を数える
                # （連鎖の先頭を探してから数える）
                # まず先頭まで戻る
                pass  # 下の先頭検出ブロックで処理

            # 連鎖先頭: 名詞系トークンで、前が「の」でない箇所
            if _is_noun_like(tok):
                prev_is_no = (i > 0 and tokens[i-1]["pos"] == "助詞"
                              and tokens[i-1]["surf"] == "の")
                if not prev_is_no:
                    # ここから「名詞系 の 名詞系 の ...」の連鎖を数える
                    no_count = 0
                    j = i + 1
                    while j + 1 < n:
                        if (tokens[j]["pos"] == "助詞"
                                and tokens[j]["surf"] == "の"
                                and _is_noun_like(tokens[j + 1])):
                            no_count += 1
                            j += 2
                        else:
                            break
                    if no_count >= _NO_CHAIN_MIN:
                        chain_start = tok["start"]
                        chain_end = tokens[j - 1]["end"] if j > i else tok["end"]
                        key = ("G1b", section_label, chain_start)
                        if key not in seen:
                            seen.add(key)
                            ctx = _get_context(text, chain_start, chain_end, window=10)
                            issues.append({
                                "milestone": "G1", "level": "info",
                                "msg": (f"「の」が{no_count}連続しています"
                                        f"（{section_label}）：「{ctx}」"),
                                "detail": ("「AのBのCのD」が長くなると読みづらくなります。"
                                           "言い換えや句の組み替えを検討してください。"),
                            })

            i += 1

    return issues


def _is_noun_like(tok: dict) -> bool:
    """名詞・代名詞・形容動詞語幹など、「の」の前後に来る名詞的要素か判定。"""
    p = tok["pos"]
    return p in ("名詞", "代名詞", "接頭辞", "形容動詞")
