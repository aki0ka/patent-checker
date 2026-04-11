# -*- coding: utf-8 -*-
"""M6: サポート要件チェック（特許法第36条6項1号）。

スコープ:
  「発明を実施するための形態」〜「実施例」末尾のみ。
  課題を解決するための手段・発明の効果・産業上の利用可能性・
  符号の説明等は対象外。
"""

from __future__ import annotations

import re

from ..tokenizer import (
    _tokenize, _is_formal_noun_tok, _collect_defined_nouns,
)


# サポート要件チェック用ストップワード
STOP_WORDS = {
    # 特許定型語
    "請求項", "記載", "発明", "特許", "明細書", "出願",
    # 複数トークン語・品詞ルールでは判定不可の限定語
    "いずれか", "少なくとも",
    "第一", "第二", "第三",
    # 照応詞・指示語
    "上記", "当該",
    # 汎用すぎて技術的特徴として意味が薄い名詞（名詞/普通名詞/一般）
    "方法", "装置", "システム", "手段", "工程",
    "情報", "データ", "信号", "構造",
    # 限定語・程度語
    "所定", "複数", "単数", "他方",
    # 汎用動作性名詞（単独では技術的特徴として弱い）
    # 複合語（受信時刻・圧縮処理等）は len>1 なので除外しない
    "ステップ", "出力", "取得", "特定",
    "処理", "構成", "送信", "受信",
}

# サポート要件チェック(M6)の監視対象スコープ終端。
_IMPL_SCOPE_END = re.compile(
    r'【(?:産業上の利用可能性|符号の説明|発明の効果|受託番号|'
    r'書類名|特許請求の範囲|図面の簡単な説明)】')


def _is_katakana_lead(text: str) -> bool:
    """先頭文字がカタカナか判定。"""
    return bool(text) and '\u30A0' <= text[0] <= '\u30FF'


def _is_valid_support_noun(noun):
    """サポート語句として有効かを品詞ベースで判定。
    先頭トークンが形式名詞・副詞可能名詞・数詞の場合は除外。
    """
    if not noun or len(noun) < 2:
        return False
    toks = _tokenize(noun)
    if not toks:
        return False
    t0 = toks[0]
    # カタカナ先行語（外来技術語）は品詞が不安定なため品詞チェックをスキップ
    if _is_katakana_lead(noun):
        return noun not in STOP_WORDS
    # 形式名詞始まり → 品詞ルールで除外
    if _is_formal_noun_tok(t0):
        return False
    # 数詞始まり（「１項」「２つ」等）は除外
    if t0['pos1'] == '数詞':
        return False
    # 接頭辞始まり（「近距離」等）は除外
    if t0['pos'] == '接頭辞':
        return False
    # STOP_WORDS残留リスト（品詞ルールで拾えない意味的除外語）
    if noun in STOP_WORDS:
        return False
    return True


def _extract_defined_nouns(text):
    """テキスト中の名詞句集合を返す（tokenizer._collect_defined_nouns のラッパー）。
    Phase 1-7 完了後は patent.anaphora.extract_defined_nouns に統合予定。
    """
    return _collect_defined_nouns(_tokenize(text))


def extract_nouns_for_support(text):
    """サポート要件チェック用の名詞抽出。品詞ベースフィルタで不適切語句を除去。"""
    # 照応詞・「請求項N」を除去してから名詞句を収集
    clean = re.sub(r'前記|上記|当該|該', '', text)
    clean = re.sub(r'請求項[０-９0-9一二三四五六七八九十１-９]+', '', clean)
    raw_nouns = _extract_defined_nouns(clean)
    # 品詞ベースフィルタ
    nouns = {n for n in raw_nouns if _is_valid_support_noun(n)}
    # 包含除去：別の語句に完全に含まれる短い語は削除
    sorted_nouns = sorted(nouns, key=len, reverse=True)
    keep = []
    for noun in sorted_nouns:
        if not any(noun in longer for longer in keep):
            keep.append(noun)
    return set(keep)


def _extract_impl_scope(desc):
    """サポート要件用: 「発明を実施するための形態」から「実施例」末尾までを抽出。"""
    start_pat = re.compile(
        r'【(?:発明を実施するための形態|発明を実施するための最良の形態|'
        r'実施例|実施の形態|実施形態)(?:[０-９\d]*)】')
    m_start = start_pat.search(desc)
    if not m_start:
        return ''
    start = m_start.start()
    m_end = _IMPL_SCOPE_END.search(desc, m_start.end())
    end = m_end.start() if m_end else len(desc)
    return desc[start:end]


def check_support(claims, sections):
    """M6: サポート要件チェック（36条6項1号）。"""
    issues = []
    desc = sections.get("description", "")
    if not desc:
        issues.append({
            "milestone": "M6", "level": "warning",
            "msg": "明細書が見つかりません"
        })
        return issues, []

    impl_text = _extract_impl_scope(desc)

    if not impl_text:
        issues.append({
            "milestone": "M6", "level": "warning",
            "msg": "「発明を実施するための形態」セクションが見つかりません。"
                   "サポート要件チェックをスキップします"
        })
        return issues, []

    support_table = []
    noun_to_claims = {}

    for num in sorted(claims.keys()):
        body = claims[num]
        nouns = extract_nouns_for_support(body)
        for n in nouns:
            if len(n) >= 2:
                noun_to_claims.setdefault(n, [])
                if num not in noun_to_claims[n]:
                    noun_to_claims[n].append(num)

    for noun in sorted(noun_to_claims.keys()):
        in_impl = noun in impl_text
        support_table.append({
            "noun":    noun,
            "claims":  noun_to_claims[noun],
            "in_impl": in_impl,
        })

    for num in sorted(claims.keys()):
        body = claims[num]
        nouns = extract_nouns_for_support(body)
        missing = sorted([n for n in nouns
                          if len(n) >= 2 and n not in impl_text])
        if missing:
            issues.append({
                "milestone": "M6", "level": "warning",
                "claim": num,
                "msg": f"請求項{num}：実施形態に未記載の語句: "
                       + "、".join(missing[:12])
                       + ("…" if len(missing) > 12 else ""),
                "missing_nouns": missing,
            })
    return issues, support_table
