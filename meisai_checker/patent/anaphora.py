# -*- coding: utf-8 -*-
"""M3: 前記・当該の照応詞チェック（特許法第36条6項2号関連）。

依存: tokenizer.py（MeCab/fugashi 必須）
"""

from __future__ import annotations

from ..tokenizer import (
    _tokenize,
    _noun_span,
    _span_to_str,
    _collect_defined_nouns,
    _noun_after_zenshou,
    _found_in_scope,
    _ZENSHOU_WORDS,
    _TOUGAI_WORDS,
)


def get_all_ancestors(num, dep_map, _cache=None):
    """指定請求項の全祖先（直接・間接の従属元）を再帰的に収集する"""
    if _cache is None:
        _cache = {}
    if num in _cache:
        return _cache[num]
    ancestors = set()
    for d in dep_map.get(num, []):
        ancestors.add(d)
        ancestors |= get_all_ancestors(d, dep_map, _cache)
    _cache[num] = ancestors
    return ancestors


def _scope_tokens_for_parent(parent, dep_map, claims, cache):
    """親請求項1つのフルスコープ（親＋その全祖先）のトークンリストを返す。"""
    anc = get_all_ancestors(parent, dep_map, cache)
    toks = []
    for a in sorted(anc | {parent}):
        toks += _tokenize(claims.get(a, ''))
    return toks


def check_zenshou(claims, dep_map):
    """前記・上記・当該・該の先行詞チェック（fugashiトークンベース）。

    スコープ：
      前記・上記 → 同一請求項の前方 ＋ 全祖先請求項
                   多項従属の場合は直接親ごとに独立してスコープを評価し、
                   全ての直接親のスコープで先行詞が見つかる場合のみOKとする
      当該・該   → 同一請求項の前方のみ
    """
    issues = []
    _cache = {}

    for num in sorted(claims.keys()):
        body = claims[num]
        tokens = _tokenize(body)

        direct_parents = dep_map.get(num, [])
        ancestors = get_all_ancestors(num, dep_map, _cache)
        ancestor_tokens = []
        for a in sorted(ancestors):
            ancestor_tokens += _tokenize(claims.get(a, ''))

        for i, t in enumerate(tokens):
            if t['surf'] not in _ZENSHOU_WORDS:
                continue
            if t['surf'] == '該' and i > 0 and tokens[i-1]['surf'] == '当':
                continue

            noun, *_ = _noun_after_zenshou(tokens, i)
            if not noun or len(noun) < 2:
                continue

            prefix = tokens[:i]  # 同一請求項の前方

            if t['surf'] in _TOUGAI_WORDS:
                # 当該・該：同一請求項の前方のみ
                scope_tokens = prefix
                found = _found_in_scope(noun, scope_tokens)
            else:
                # 前記・上記
                # まず同一請求項の前方で見つかれば常にOK
                if _found_in_scope(noun, prefix):
                    continue
                if len(direct_parents) <= 1:
                    # 単項従属または独立：全祖先を結合してチェック
                    found = _found_in_scope(noun, ancestor_tokens)
                else:
                    # 多項従属：全ての直接親のスコープそれぞれで見つかる必要がある
                    found = all(
                        _found_in_scope(noun, _scope_tokens_for_parent(p, dep_map, claims, _cache))
                        for p in direct_parents
                    )
                scope_tokens = ancestor_tokens + prefix  # エラーメッセージ用

            if not found:
                suppressed = False
                if t['surf'] in _TOUGAI_WORDS:
                    for j, tj in enumerate(prefix):
                        if tj['surf'] in ('前記', '上記'):
                            prev_noun, *_ = _noun_after_zenshou(tokens, j)
                            if prev_noun == noun:
                                prev_scope = ancestor_tokens + tokens[:j]
                                if _found_in_scope(noun, prev_scope):
                                    suppressed = True
                                    break
                if not suppressed:
                    if t['surf'] not in _TOUGAI_WORDS and len(direct_parents) > 1:
                        # 多項従属の場合、どの親で見つからないかを示す
                        missing = [p for p in direct_parents
                                   if not _found_in_scope(noun,
                                       _scope_tokens_for_parent(p, dep_map, claims, _cache))]
                        detail = f"（請求項{missing}に従属する場合にスコープ外）"
                    elif t['surf'] not in _TOUGAI_WORDS:
                        dep_chain = sorted(ancestors)
                        detail = (f"（参照先：同一請求項前方＋従属元{dep_chain}）"
                                  if dep_chain else "")
                    else:
                        detail = "（当該・該のスコープは従属元を含みません）"
                    issues.append({
                        'claim': num, 'level': 'error',
                        'word': t['surf'], 'noun': noun,
                        'msg': f"請求項{num}：「{t['surf']}{noun}」の先行詞がスコープ内に見つかりません{detail}",
                    })
    return issues


# check_zenshou から参照される旧API互換ラッパー
def extract_noun_phrase_after(text, pos):
    """旧API互換：pos以降の名詞句を (noun, consumed) で返す。"""
    tokens = _tokenize(text[pos:])
    span = _noun_span(tokens, 0)
    noun = _span_to_str(span)
    consumed = len(noun)
    return noun, consumed


def extract_defined_nouns(text):
    """テキスト中の名詞句集合を返す（_collect_defined_nounsのテキスト版ラッパー）。"""
    tokens = _tokenize(text)
    return _collect_defined_nouns(tokens)


def build_noun_groups(claims, dep_map, ref_hits, m3_issues):
    """
    名詞句ごとにグループ化した前記チェック情報を返す。
    各グループ：
    {
      "noun":        "通行人",
      "error":       False,       # いずれかの参照がエラーなら True
      "first_claim": 1,           # 初出請求項番号（先行詞がある最初の請求項）
      "refs": [                   # この名詞句への「前記」出現一覧
        {"claim": 2, "word": "前記", "error": False},
        ...
      ]
    }
    """
    # m3_issueのエラーセット: (claim, noun, word)
    # word を含めることで「前記物体」(正常)と「当該物体」(エラー)を区別する
    error_set = {(i['claim'], i['noun'], i.get('word', '')) for i in m3_issues
                 if i.get('level') == 'error'}
    # 互換用: (claim, noun) のみのセット（wordなしのissueに対応）
    error_set_no_word = {(i['claim'], i['noun']) for i in m3_issues
                         if i.get('level') == 'error' and 'word' not in i}

    # ref_hitsを名詞句でグループ化
    groups = {}  # noun → group dict
    for hit in ref_hits:
        noun = hit['noun']
        if len(noun) < 2:
            continue
        if noun not in groups:
            groups[noun] = {
                'noun': noun,
                'error': False,
                'first_claim': None,
                'refs': [],
            }
        is_err = ((hit['claim'], noun, hit['word']) in error_set or
                  (hit['claim'], noun) in error_set_no_word)
        groups[noun]['refs'].append({
            'claim': hit['claim'],
            'word':  hit['word'],
            'pos':   hit.get('pos', 0),   # 請求項内文字位置
            'error': is_err,
        })
        if is_err:
            groups[noun]['error'] = True

    # 初出請求項を特定
    def _find_first_in(noun, target_nums):
        from ..tokenizer import _LOC_SUFFIXES
        candidates = [noun]
        # 位置接尾辞フォールバック:
        # 「収容部内」→「収容部」も候補に追加
        # UniDicが「部内」を複合名詞として一体化した場合、定義語は「収容部」であり
        # 請求項本文に「収容部内」という語句は現れないため完全一致検索が失敗する
        if noun and noun[-1] in _LOC_SUFFIXES and len(noun) > 2:
            base = noun[:-1]
            if len(base) >= 2:
                candidates.append(base)
        for num in target_nums:
            body = claims.get(num)
            if body is None:
                continue
            for cand in candidates:
                idx = 0
                while True:
                    pos = body.find(cand, idx)
                    if pos < 0:
                        break
                    prefix = body[max(0, pos-2):pos]
                    if prefix not in ('前記', '上記', '当該') and body[max(0,pos-1):pos] != '該':
                        return num
                    idx = pos + 1
        return None

    for noun, g in groups.items():
        # 全refにref個別のfirst_claimを設定する
        # スコープ規則：
        #   前記/上記 → 同一請求項 ＋ 直接・間接の全従属元（get_all_ancestors）
        #   当該/該   → 同一請求項のみ
        #              ただし同一請求項前方に「前記N」（エラーなし）があれば祖先まで拡張
        g['first_claim'] = None  # グループレベルは使わない（UI互換のため後でも設定）
        for r in g['refs']:
            # キャッシュなしで呼び出し（各ref個別に計算）
            ancestors = get_all_ancestors(r['claim'], dep_map)
            if r['word'] in ('当該', '該'):
                # 当該拡張ルール: 同一請求項前方に正常な「前記N」があれば祖先スコープも使用
                claim_tokens = _tokenize(claims.get(r['claim'], ''))
                anc_tokens = []
                for a in sorted(ancestors):
                    anc_tokens += _tokenize(claims.get(a, ''))
                # 同一請求項の前方トークン列で「前記N」を探す
                suppressed_first = None
                for j, tj in enumerate(claim_tokens):
                    if tj['surf'] in ('前記', '上記'):
                        prev_noun, _ = _noun_after_zenshou(claim_tokens, j)
                        if prev_noun == noun:
                            prev_scope = anc_tokens + claim_tokens[:j]
                            if _found_in_scope(noun, prev_scope):
                                # 「前記N」が正常 → 祖先スコープで先行詞を探せる
                                suppressed_first = _find_first_in(noun, sorted(ancestors | {r['claim']}))
                                break
                if suppressed_first is not None:
                    scope_nums = sorted(ancestors | {r['claim']})
                else:
                    scope_nums = [r['claim']]
            else:
                scope_nums = sorted(ancestors | {r['claim']})
            # エラー行（先行詞なし）はfirst_claim=Noneに固定
            if r['error']:
                r['first_claim'] = None
            else:
                r['first_claim'] = _find_first_in(noun, scope_nums)
        # first_claim=None かつ error=False → 先行詞が見つからなかった → エラーに補正
        for r in g['refs']:
            if not r['error'] and r['first_claim'] is None:
                r['error'] = True
        # グループレベルのfirst_claim: refのfirst_claimの最小値（フォールバック用）
        valid = [r['first_claim'] for r in g['refs'] if r['first_claim'] is not None]
        g['first_claim'] = min(valid) if valid else None

    # 全 (group, ref) をフラット化して請求項昇順→noun名昇順でソートして返す
    for g in groups.values():
        g['refs'].sort(key=lambda r: r['claim'])
    return sorted(groups.values(), key=lambda g: (g['refs'][0]['claim'] if g['refs'] else 0, g['noun']))
