# -*- coding: utf-8 -*-
"""ビューア用ブロック構築・HTMLハイライトモジュール。

build_blocks / _highlight_claim / _highlight_para を提供する。
GUI・CLI・MCP サーバーから共通利用される表示層ロジック。

依存: patent.anaphora (extract_noun_phrase_after), patent.fugo (_extract_elements_tokens)
"""

from __future__ import annotations

import re
from collections import defaultdict

from .patent.anaphora import extract_noun_phrase_after
from .tokenizer import _tokenize, _noun_after_zenshou
from .patent.fugo import _extract_elements_tokens


def build_blocks(text, claims, m3_issues, m4_issues, element_table, ref_hits=None, noun_groups=None):
    """
    本文をブロック（段落単位/請求項単位）に分割し、
    各ブロックにハイライト情報を付与して返す。
    block = {
      "id":      "p-0001" | "c-1",
      "type":    "para" | "claim" | "section",
      "label":   "【0001】" | "請求項1",
      "text":    本文テキスト,
      "html":    ハイライト済みHTML,
      "issues":  [issue, ...],  # このブロックに関連するissue
    }
    """
    blocks = []

    # ── 前記チェックのエラーセット構築 ──
    m3_error_nouns = set()  # エラーになった（claim, noun）
    for iss in m3_issues:
        if iss.get('level') == 'error':
            m3_error_nouns.add((iss['claim'], iss['noun']))

    # ── 符号の正常/エラーセット構築 ──
    # fugo_to_names: {符号: [要素名, ...]}
    fugo_to_names = {}
    for e in element_table:
        for f in e['fugos']:
            fugo_to_names.setdefault(f, set()).add(e['name'])
    fugo_errors = {f for f, ns in fugo_to_names.items() if len(ns) > 1}

    # ── 初出名詞句マップ構築 ──
    # noun_groupsのref個別first_claimを使い、各請求項が「先行詞として定義」する名詞句を収集
    # スコープ規則（前記→従属チェーン内、当該→同一請求項）はbuild_noun_groupsで計算済み
    first_nouns_by_claim = defaultdict(set)
    if noun_groups:
        for g in noun_groups:
            for r in g['refs']:
                # ref個別のfirst_claim（当該/該はref単位、前記はスコープ限定済み）
                fc = r.get('first_claim')
                if fc is None:
                    fc = g.get('first_claim')
                if fc is not None:
                    first_nouns_by_claim[fc].add(g['noun'])
    else:
        # noun_groupsがない場合のフォールバック（全請求項横断・後方互換）
        if ref_hits is None:
            ref_hits = []
        candidate_nouns = {hit['noun'] for hit in ref_hits if len(hit.get('noun','')) >= 2}
        for noun in candidate_nouns:
            for num in sorted(claims.keys()):
                body = claims[num]
                idx = 0
                while True:
                    pos = body.find(noun, idx)
                    if pos < 0:
                        break
                    prefix = body[max(0, pos-2):pos]
                    prev1  = body[max(0, pos-1):pos]
                    if prefix not in ('前記', '上記', '当該') and prev1 != '該':
                        first_nouns_by_claim[num].add(noun)
                        break
                    idx = pos + 1
                if noun in {n for s in first_nouns_by_claim.values() for n in s}:
                    break

    # ── 請求項ブロック ──
    for num in sorted(claims.keys()):
        body = claims[num]
        # このブロックに関連するissue
        related = [iss for iss in m3_issues + m4_issues
                   if iss.get('claim') == num]
        blocks.append({
            "id":     f"c-{num}",
            "type":   "claim",
            "label":  f"請求項{num}",
            "text":   body,
            "html":   _highlight_claim(body, num, m3_error_nouns, fugo_errors,
                                        element_table, first_nouns_by_claim.get(num, set())),
            "issues": related,
            "section": "claims",
        })

    # ── 段落ブロック ──
    para_pat = re.compile(r'(【(\d{4})】)(.*?)(?=【\d{4}】|【[^０-９0-9\d]|$)', re.DOTALL)
    desc_text = text  # 全体から段落を拾う
    for m in para_pat.finditer(desc_text):
        label = m.group(1)
        num_str = m.group(2)
        body = m.group(3).strip()
        if not body:
            continue
        pid = f"p-{num_str}"
        related = []  # 段落に直接紐づくissueは現状なし
        blocks.append({
            "id":      pid,
            "type":    "para",
            "label":   label,
            "text":    body,
            "html":    _highlight_para(body, fugo_errors, element_table),
            "issues":  related,
            "section": "description",
        })

    return blocks


def _highlight_claim(text, claim_num, m3_error_nouns, fugo_errors, element_table, first_nouns=None):
    """請求項テキストに前記/当該/符号のハイライトを付与してHTMLを返す"""
    import html as html_mod

    if first_nouns is None:
        first_nouns = set()
    out = []
    i = 0
    esc = html_mod.escape
    while i < len(text):
        matched = False
        # 初出名詞句ハイライト（前記なしで出現 → 黄色枠）
        for fn in sorted(first_nouns, key=len, reverse=True):
            if text[i:i+len(fn)] == fn:
                prefix = text[max(0,i-2):i]
                prev1  = text[max(0,i-1):i]
                if prefix not in ('前記','上記','当該') and prev1 != '該':
                    out.append(f'<span class="hl-first-noun" data-noun="{esc(fn)}">{esc(fn)}</span>')
                    i += len(fn)
                    matched = True
                    break
        if matched:
            continue
        # 前記・上記・当該 ＋ 名詞句 → 全体を1スパン（水色、動詞スキップ部は紫）
        for word in ['前記', '上記', '当該']:
            if text[i:i+len(word)] == word:
                sub_toks = _tokenize(text[i:])
                noun, noun_rel_start, noun_rel_end = _noun_after_zenshou(sub_toks, 0)
                is_err = (claim_num, noun) in m3_error_nouns
                cls = 'hl-zenshou-err' if is_err else 'hl-zenshou'
                safe_noun = esc(noun) if noun else ''
                if noun and noun_rel_start > len(word):
                    gap  = esc(text[i + len(word) : i + noun_rel_start])
                    body = esc(text[i + noun_rel_start : i + noun_rel_end])
                    inner = f'{esc(word)}<span class="hl-zenshou-skip">{gap}</span>{body}'
                else:
                    inner = esc(text[i : i + noun_rel_end]) if noun else esc(word)
                out.append(f'<span class="{cls}" data-noun="{safe_noun}" data-claim="{claim_num}">{inner}</span>')
                i += noun_rel_end if noun else len(word)
                matched = True
                break
        if not matched:
            # 該（当該以外）＋ 名詞句 → 全体を1スパン（水色、動詞スキップ部は紫）
            if text[i:i+1] == '該' and (i == 0 or text[i-2:i] != '当該'):
                sub_toks = _tokenize(text[i:])
                noun, noun_rel_start, noun_rel_end = _noun_after_zenshou(sub_toks, 0)
                is_err = (claim_num, noun) in m3_error_nouns
                cls = 'hl-zenshou-err' if is_err else 'hl-zenshou'
                safe_noun = esc(noun) if noun else ''
                if noun and noun_rel_start > 1:
                    gap  = esc(text[i + 1 : i + noun_rel_start])
                    body = esc(text[i + noun_rel_start : i + noun_rel_end])
                    inner = f'該<span class="hl-zenshou-skip">{gap}</span>{body}'
                else:
                    inner = esc(text[i : i + noun_rel_end]) if noun else '該'
                out.append(f'<span class="{cls}" data-noun="{safe_noun}" data-claim="{claim_num}">{inner}</span>')
                i += noun_rel_end if noun else 1
            else:
                out.append(esc(text[i]))
                i += 1
    return ''.join(out).replace('\n', '<br>')


def _highlight_para(text, fugo_errors, element_table):
    """段落テキストに符号ハイライトを付与してHTMLを返す。
    _extract_elements_tokens は (name, fugo, char_offset) を返す。
    char_offsetベースでテキストを直接スキャンしてスパンを挿入する。
    """
    import html as html_mod
    esc = html_mod.escape

    # (name, fugo, char_offset) をオフセット順にソート
    drawing, _ = _extract_elements_tokens(text)
    pairs = sorted(drawing, key=lambda x: x[2])
    if not pairs:
        return esc(text).replace('\n', '<br>')

    out = []
    pos = 0
    for row in pairs:
        name, fugo, offset = row[0], row[1], row[2]
        key = name + fugo
        # offsetが実際のテキスト位置と一致しているか確認
        if text[offset:offset+len(key)] != key:
            # ずれている場合は直近で再探索
            found = text.find(key, pos)
            if found < 0:
                continue
            offset = found
        if offset < pos:
            continue  # 重複スキップ
        out.append(esc(text[pos:offset]))
        is_err = fugo in fugo_errors
        cls = 'hl-fugo-err' if is_err else 'hl-fugo'
        out.append(f'<span class="{cls}" data-name="{esc(name)}" data-fugo="{esc(fugo)}">'
                   f'{esc(name)}<span class="fugo-num">{esc(fugo)}</span></span>')
        pos = offset + len(key)
    out.append(esc(text[pos:]))
    return ''.join(out).replace('\n', '<br>')
