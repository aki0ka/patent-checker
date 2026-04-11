# -*- coding: utf-8 -*-
"""
特許明細書方式チェッカー - 解析・検証モジュール
各種チェック関数と分析ロジックを集約
"""

import re
from collections import defaultdict, Counter

from .preprocessor import normalize, NormalizedDoc, DocFormat
from .parser import (
    split_sections, parse_claims, parse_dependencies, extract_invention_type,
    classify_claims, KIND_INDEPENDENT, KIND_SINGLE_DEP, KIND_MULTI, KIND_MULTI_MULTI,
    z2h, check_dependency
)
from .tokenizer import (
    _tokenize, _is_noun_tok, _is_formal_noun_tok, _strip_quant_prefix,
    _noun_span, _span_to_str, _collect_defined_nouns, _noun_after_zenshou,
    _found_in_scope, _is_fugo_tok, _is_alpha_fugo_tok,
    _ZENSHOU_WORDS, _TOUGAI_WORDS, _ORDINAL_MODS
)

# ── Phase 1 リファクタリング: 移動済み関数の再エクスポート（後方互換）
# 新規コードは個別モジュールから直接 import すること。
from .textcheck.kuten import check_kuten, _is_kuten_exempt, _KUTEN_EXEMPT_PATS  # noqa: F401
from .textcheck.charset import (  # noqa: F401
    check_jis, _jis_char_status, _section_label, _JIS_ALTERNATIVES,
)
from .structure.abstract import check_abstract  # noqa: F401
from .patent.title import check_title  # noqa: F401
from .structure.sections import (  # noqa: F401
    check_structure, check_para_nums, check_midashi_numbers,
    _heading_type, _HEADING_TYPE1, _HEADING_TYPE2, _HEADING_TYPE2_NOCHECK,
    _HEADING_TYPE3, _HEADING_TYPE4_PAT, _MEISHO_ITEMS, _NO_PARA_BETWEEN,
)
from .patent.support import (  # noqa: F401
    check_support, extract_nouns_for_support, STOP_WORDS, _IMPL_SCOPE_END,
    _extract_impl_scope, _is_valid_support_noun,
)
from .patent.anaphora import (  # noqa: F401
    get_all_ancestors, check_zenshou, extract_noun_phrase_after,
    extract_defined_nouns, build_noun_groups,
)
from .patent.fugo import (  # noqa: F401
    check_fugo, check_fugo_setsumeisho, classify_fugo, FUGO_EXCLUDE_LIST,
    _is_fugo_exclude, _is_fugo_exclude_tok, _is_koho_name, _is_koho_name_part,
    _parse_fugo_setsumeisho, _extract_elements_tokens, _collect_fugo_suffix,
    _offset_to_para_id, _lineno_to_para_id,
    _KOHO_PAT, _KOHO_PART_PAT, _KOHO_SUFFIX,
    _is_zenkaku_digit, _is_zenkaku_upper, _is_zenkaku_lower,
    _is_zenkaku_alpha, _is_half_digit, _is_katakana_lead,
)
from .blocks import build_blocks, _highlight_claim, _highlight_para  # noqa: F401
from .textcheck.brackets import check_brackets
from .textcheck.repetition import check_repetition
from .textcheck.style import check_style
from .textcheck.length import check_length


# ══════════════════════════════════════════════════════════
# メイン解析
# ══════════════════════════════════════════════════════════

def analyze(text):
    """明細書テキストを完全解析。"""
    # 改行コード正規化: CRLF→LF, CR単独→LF
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    sections  = split_sections(text)
    claims    = parse_claims(sections.get('claims', text))
    lines     = text.splitlines()
    para_nums = re.findall(r'【\d{4}】', text)

    # 従属マップ
    dep_map = {num: [d for d in parse_dependencies(body) if d != num]
               for num, body in claims.items()}

    # 種別判定
    kinds = classify_claims(claims, dep_map)

    # 発明種類
    inv_types = {num: extract_invention_type(body)
                 for num, body in claims.items()}

    # 統計
    cnt = {k: 0 for k in [KIND_INDEPENDENT, KIND_SINGLE_DEP,
                            KIND_MULTI, KIND_MULTI_MULTI]}
    for k in kinds.values():
        cnt[k] += 1

    # クレームリスト
    claim_list = []
    for num in sorted(claims.keys()):
        deps  = dep_map.get(num, [])
        kind  = kinds[num]
        body  = claims[num]
        claim_list.append({
            "num":      num,
            "kind":     kind,
            "is_error": kind == KIND_MULTI_MULTI,
            "deps":     deps,
            "inv_type": inv_types[num],
            "preview":  re.sub(r'\s+', ' ', body)[:80],
        })

    # 前記・当該の出現一覧（M3表示用）
    ref_hits = []
    for num, body in sorted(claims.items()):
        body_tokens = _tokenize(body)
        for i, t in enumerate(body_tokens):
            if t['surf'] not in ('前記', '上記', '当該', '該'):
                continue
            if t['surf'] == '該' and i > 0 and body_tokens[i-1]['surf'] == '当':
                continue  # 「当該」の「該」はスキップ
            word = t['surf']
            noun = _noun_after_zenshou(body_tokens, i)
            if len(noun) < 2:
                continue
            # context: 前後の生テキストから取得
            char_pos = t['start']
            context = body[max(0, char_pos-12): char_pos+len(word)+len(noun)+12
                          ].replace("\n", " ").replace("\r", "")
            ref_hits.append({
                "claim":   num,
                "word":    word,
                "noun":    noun,
                "pos":     char_pos,
                "context": context,
            })

    # 各チェック実行
    m2_issues = check_dependency(claims, dep_map, kinds)
    m3_issues = check_zenshou(claims, dep_map)
    m4_issues, element_table, fugo_table, var_table = check_fugo(claims, sections)
    setsu_issues, setsu_table = check_fugo_setsumeisho(fugo_table, text)
    m4_issues = m4_issues + setsu_issues
    # check_jis: sections に加えて生テキストの改ページ等も検出
    _raw_sections = dict(sections)
    _raw_sections['_raw'] = text  # 生テキスト（改ページ等が残っている）
    jis_issues      = check_jis(_raw_sections)
    struct_issues   = check_structure(text)
    para_issues     = check_para_nums(text)
    kuten_issues    = check_kuten(sections)
    abstract_issues = check_abstract(sections)
    midashi_issues  = check_midashi_numbers(sections)
    m5_issues, title, title_inv_types = check_title(sections, claim_list)
    m5_issues = struct_issues + para_issues + abstract_issues + midashi_issues + kuten_issues + jis_issues + m5_issues
    m6_issues, support_table = check_support(claims, sections)

    # M7: 係り受け曖昧性チェック（遅延インポートで依存を分離）
    try:
        from .patent.ambiguity import check_ambiguity
        m7_issues = check_ambiguity(claims)
    except Exception:
        m7_issues = []

    # M8: 記録項目チェック（遅延インポートで依存を分離）
    try:
        from .structure.docfields import check_docfields
        m8_issues = check_docfields(text)
    except Exception:
        m8_issues = []

    # TC: 文章形式チェック（Layer 2: MeCab不要、正規表現のみ）
    tc_issues = (check_brackets(sections) +
                 check_repetition(sections) +
                 check_style(sections) +
                 check_length(sections))

    all_issues = m2_issues + m3_issues + m4_issues + m5_issues + m6_issues + m7_issues + m8_issues + tc_issues

    noun_groups = build_noun_groups(claims, dep_map, ref_hits, m3_issues)

    # 40文字×50行=1ページ計算（禁則処理なし）
    COLS, ROWS = 40, 50
    page_lines = 0
    for raw_line in lines:
        # 1行を40文字ごとに折り返した配置行数
        page_lines += max(1, -(-len(raw_line) // COLS))  # ceiling division
    total_pages = max(1, -(-page_lines // ROWS))

    return {
        "stats": {
            "total_chars":    len(text),
            "total_lines":    len(lines),
            "page_lines":     page_lines,
            "total_pages":    total_pages,
            "total_paras":    len(para_nums),
            "total_claims":   len(claims),
            KIND_INDEPENDENT: cnt[KIND_INDEPENDENT],
            KIND_SINGLE_DEP:  cnt[KIND_SINGLE_DEP],
            KIND_MULTI:       cnt[KIND_MULTI],
            KIND_MULTI_MULTI: cnt[KIND_MULTI_MULTI],
        },
        "claim_list":       claim_list,
        "ref_hits":         ref_hits,
        "issues": {
            "m2": m2_issues,
            "m3": m3_issues,
            "m4": m4_issues,
            "m5": m5_issues,
            "m6": m6_issues,
            "m7": m7_issues,
            "m8": m8_issues,
            "tc": tc_issues,
            "all": all_issues,
        },
        "element_table":    element_table,
        "fugo_table":       fugo_table,
        "var_table":        var_table,
        "setsu_table":      setsu_table,
        "support_table":    support_table,
        "title":            title,
        "title_inv_types":  title_inv_types,
        "blocks":           build_blocks(text, claims, m3_issues, m4_issues,
                                         element_table, ref_hits, noun_groups),
        "noun_groups":      noun_groups,
    }


