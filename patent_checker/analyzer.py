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


# ══════════════════════════════════════════════════════════
# ヘルパー関数
# ══════════════════════════════════════════════════════════

def _is_zenkaku_digit(c):
    """全角数字か判定"""
    return '\uff10' <= c <= '\uff19'

def _is_zenkaku_upper(c):
    """全角大文字か判定"""
    return '\uff21' <= c <= '\uff3a'

def _is_zenkaku_lower(c):
    """全角小文字か判定"""
    return '\uff41' <= c <= '\uff5a'

def _is_zenkaku_alpha(c):
    """全角英字か判定"""
    return _is_zenkaku_upper(c) or _is_zenkaku_lower(c)

def _is_half_digit(s):
    """半角数字を含むか"""
    return any('0' <= c <= '9' for c in s)

def _is_katakana_lead(s):
    """文字列の先頭がカタカナ（全角）か判定"""
    return bool(s) and ('\u30A0' <= s[0] <= '\u30FF')


# ══════════════════════════════════════════════════════════
# M3: 前記・当該チェック
# ══════════════════════════════════════════════════════════

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


def check_zenshou(claims, dep_map):
    """前記・上記・当該・該の先行詞チェック（fugashiトークンベース）。

    スコープ：
      前記・上記 → 同一請求項の前方 ＋ 全祖先請求項
      当該・該   → 同一請求項の前方のみ
    """
    issues = []
    # 共有キャッシュを作成（複数のget_all_ancestors呼び出しで再利用）
    _cache = {}

    for num in sorted(claims.keys()):
        body = claims[num]
        tokens = _tokenize(body)

        ancestors = get_all_ancestors(num, dep_map, _cache)
        # 祖先テキストをトークン化してスコープとして使う
        ancestor_tokens = []
        for a in sorted(ancestors):
            ancestor_tokens += _tokenize(claims.get(a, ''))

        for i, t in enumerate(tokens):
            if t['surf'] not in _ZENSHOU_WORDS:
                continue
            # 「該」が「当該」の一部でないか確認
            if t['surf'] == '該' and i > 0 and tokens[i-1]['surf'] == '当':
                continue

            noun = _noun_after_zenshou(tokens, i)
            if not noun or len(noun) < 2:
                continue

            # スコープトークンを決定
            if t['surf'] in _TOUGAI_WORDS:
                # 当該・該：同一請求項の前方のみ
                scope_tokens = tokens[:i]
            else:
                # 前記・上記：祖先 + 同一請求項の前方
                scope_tokens = ancestor_tokens + tokens[:i]

            if not _found_in_scope(noun, scope_tokens):
                # 当該・該の拡張ルール:
                # 同一請求項の前方に「前記N」or「上記N」があり、
                # かつその「前記N」がエラーでない（祖先スコープに先行詞あり）場合は許可
                suppressed = False
                if t['surf'] in _TOUGAI_WORDS:
                    # 同一請求項前方に「前記N」または「上記N」があるか確認
                    for j, tj in enumerate(tokens[:i]):
                        if tj['surf'] in ('前記', '上記'):
                            prev_noun = _noun_after_zenshou(tokens, j)
                            if prev_noun == noun:
                                # この「前記N」自体がエラーでないか確認
                                prev_scope = ancestor_tokens + tokens[:j]
                                if _found_in_scope(noun, prev_scope):
                                    suppressed = True
                                    break
                if not suppressed:
                    dep_chain = sorted(ancestors) if t['surf'] not in _TOUGAI_WORDS else []
                    issues.append({
                        'claim': num, 'level': 'error',
                        'word': t['surf'], 'noun': noun,
                        'msg': (f"請求項{num}：「{t['surf']}{noun}」の先行詞が"
                                f"スコープ内に見つかりません"
                                + (f"（参照先：同一請求項前方＋従属元{dep_chain}）"
                                   if dep_chain else "（当該・該のスコープは従属元を含みません）"))
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


# ══════════════════════════════════════════════════════════
# M4: 符号チェック
# ══════════════════════════════════════════════════════════

# 除外語：これらを含む名詞列は符号として扱わない
_KOHO_PAT = re.compile(
    r'^(?:特開|特公|特許|特願|実開|実公|実願|国際公開|WO|JP)'
    r'(?:昭|平|令|和)?'
)
_KOHO_PART_PAT = re.compile(
    r'^(?:開|公|報|昭|平|令|和)(?:昭|平|令|和|開|公|報)?'
)
_KOHO_SUFFIX = {'公報', '号', '号公報', '公開'}

FUGO_EXCLUDE_LIST = {
    # 参照番号接頭語（「図１」「表２」「段落【0001】」等）
    '図', '表', '式', '数式', '段落', '頁', 'ページ', '第', '項',
    # 特許定型語
    '特許', '請求項',
    # 手順参照語（ステップＳ→変数記号誤検出防止）
    'ステップ',
    # 数量・変化語（「数１」「化１」等の誤検出防止）
    '数', '化', '乃至',
    # 日付・年号（「平成３年」「昭和２０年」「令和５年」等）
    '年', '月', '日', '平成', '昭和', '令和',
}


def _is_koho_name(name):
    """公報番号の冒頭パターンに該当する要素名か判定。"""
    return bool(_KOHO_PAT.match(name))


def _is_koho_name_part(name):
    """公報番号トークン分割後の残り部分（開昭・開平等）か判定。"""
    return bool(_KOHO_PART_PAT.match(name)) or name in _KOHO_SUFFIX


def _is_fugo_exclude_tok(tok):
    """トークン単体がFUGO除外対象か（品詞ルール）。"""
    p, p2 = tok['pos'], tok.get('pos2', '*')
    # 動詞（化・向け等）
    if p == '動詞':
        return True
    # 副詞可能名詞（うち等）
    if p == '名詞' and p2 == '副詞可能':
        return True
    return False


def _is_fugo_exclude(name, toks=None):
    """要素名（名詞句全体）がFUGO除外対象か判定。
    name: 結合済み文字列
    toks: name を構成するトークンリスト（あれば品詞ルールも適用）

    ※ トークン単体の「全トークン走査」チェックは廃止。
       「位置表」の「表」のように複合語末尾に参照番号接頭語が来る場合の
       誤除外を防ぐため、先頭トークンのみをチェックする。
    """
    # 名前全体のリスト完全一致
    if name in FUGO_EXCLUDE_LIST:
        return True
    # 末尾パターン
    if name.endswith('文献'):
        return True
    if name.endswith('例'):
        return True
    if name.endswith('形態'):
        return True
    # 国際特許分類（Ａ３１Ｂ７／０２等）
    if name.startswith('国際特許分類'):
        return True
    # 全角大文字4文字以上の技術規格略称（ＩＥＥＥ, ＣＤＭＡ等）を除外
    if len(name) >= 4 and all(_is_zenkaku_upper(c) for c in name):
        return True
    # 公報番号パターン
    if _is_koho_name(name) or _is_koho_name_part(name):
        return True
    # 先頭トークンがリストに含まれる場合（「ステップＳ」→先頭「ステップ」等）
    if toks and toks[0]['surf'] in FUGO_EXCLUDE_LIST:
        return True
    # カタカナ先行語は品詞が不安定なため品詞ルールをスキップ
    if _is_katakana_lead(name):
        return False
    # 1トークンの品詞ルール（副詞可能・動詞等）
    if toks and len(toks) == 1 and _is_fugo_exclude_tok(toks[0]):
        return True
    return False


def classify_fugo(fugo):
    """符号文字列を分類して返す。
    戻り値: 'drawing'（図面符号）| 'variable'（変数記号）| None（無視）

    図面符号:
      (A) 全角数字始まり + 末尾に全角英字0〜2文字
          例: １２、１２ａ、１３Ｂ
      (B) 全角英字2文字以上始まり + 全角数字列
          例: ＣＰＵ１０、ＶＲＡＭ１３３、ＬＥＤ２５

    変数記号:
      全角英字ちょうど1文字 + (全角数字 or 半角英数字)*
      例: Ｖ、ｔ、Ｖ０、Ｔmax、Ｉ１
    """
    if not fugo:
        return None
    c0 = fugo[0]

    # パターン(A): 全角数字始まり
    if _is_zenkaku_digit(c0):
        # 数字部分
        k = 0
        while k < len(fugo) and _is_zenkaku_digit(fugo[k]):
            k += 1
        # ハイフン付きサフィックス: －数字列 または －英字1〜2文字 または －ｎ等
        if k < len(fugo) and fugo[k] == '－':
            rest = fugo[k+1:]
            # サフィックスが全角数字列・全角英字1〜2文字・全角小文字英字(ｎ等)のいずれか
            if rest and (
                all(_is_zenkaku_digit(c) for c in rest) or
                (len(rest) <= 2 and all(_is_zenkaku_alpha(c) for c in rest))
            ):
                return 'drawing'
            return None
        # 残りは全角英字0〜2文字まで
        suffix = fugo[k:]
        if len(suffix) <= 2 and all(_is_zenkaku_alpha(c) for c in suffix):
            return 'drawing'
        return None

    # パターン(B): 全角英字2文字以上始まり
    if _is_zenkaku_alpha(c0):
        alpha_len = 0
        while alpha_len < len(fugo) and _is_zenkaku_alpha(fugo[alpha_len]):
            alpha_len += 1
        if alpha_len >= 2:
            # 全角大文字のみ（Ｗｉ-Ｆｉ等の小文字混在ケースを除外）
            if not all(_is_zenkaku_upper(fugo[k]) for k in range(alpha_len)):
                return None
            # 残りが全角数字列
            rest = fugo[alpha_len:]
            if rest and all(_is_zenkaku_digit(c) for c in rest):
                return 'drawing'
            # 数字なしの純英字略称（ＣＰＵ単体等）はスルー
            return None
        # 全角英字1文字始まり → 変数記号
        # 添字: 全角数字 or 半角英数字
        rest = fugo[1:]
        if all(_is_zenkaku_digit(c) or c.isascii() and c.isalnum() or c == '_' for c in rest):
            return 'variable'
        return None

    return None


def _collect_fugo_suffix(tokens, start_idx):
    """トークンリストから符号サフィックスを収集するヘルパー。
    戻り値: (サフィックス部品リスト, 次のインデックス)
    """
    fugo_parts = []
    j = start_idx
    n = len(tokens)

    # 全角数詞列を収集
    while j < n and _is_fugo_tok(tokens[j]):
        fugo_parts.append(tokens[j]['surf'])
        j += 1

    # 小数点（全角ピリオド）が続く場合は数値表現（電圧１．０Ｖ等）として符号ではない
    if j < n and tokens[j]['surf'] in ('．', '.'):
        return [], j

    # ハイフン付きサフィックス: 全角数詞の後に「－」＋数詞/名詞
    # 例: １００３－１, １００３－ｎ, １００１－Ａ
    if (j + 1 < n
            and tokens[j]['surf'] == '－'
            and tokens[j]['pos'] == '補助記号'):
        nxt = tokens[j+1]
        nxt_s = nxt['surf']
        # サフィックス: 全角数字列 or 全角英字1〜2文字
        if (all(_is_zenkaku_digit(c) for c in nxt_s) or
                (len(nxt_s) <= 2 and all(_is_zenkaku_alpha(c) for c in nxt_s))):
            fugo_parts.append('－')
            fugo_parts.append(nxt_s)
            j += 2

    # サフィックス（全角英字1〜2文字、ハイフンなし）
    elif j < n and _is_alpha_fugo_tok(tokens[j]):
        next_tok = tokens[j + 1] if j + 1 < n else None
        next_surf = next_tok['surf'] if next_tok else ''
        # 「以外」「以上」「以下」「など」等の後置語は次の要素名ではないのでサフィックスを収集する
        _alpha_allow_next = {'以外', '以上', '以下', '以内', 'など', '等', 'を', 'に', 'の', 'は', 'が', 'も', 'で', 'と', 'へ', 'より'}
        if (next_tok is not None
                and _is_noun_tok(next_tok)
                and next_tok['pos1'] != '数詞'
                and next_surf not in _alpha_allow_next):
            # 次が名詞の場合はスキップ（要素名扱い）
            pass
        else:
            fugo_parts.append(tokens[j]['surf'])
            j += 1
    elif j < n and _is_noun_tok(tokens[j]) and tokens[j]['pos1'] != '数詞' and tokens[j]['pos'] != '接尾辞':
        # 名詞が来た場合もスキップ（次の要素名扱い）
        pass

    return fugo_parts, j


def _extract_elements_tokens(text):
    """テキストをトークン化し（要素名, 符号, char_offset）ペアを返す。

    符号パターン:
      図面符号(A): 全角数字列 + (全角英字0〜2文字)?  例: １２、１２ａ、１３Ｂ
      図面符号(B): 全角英字2文字以上 + 全角数字列    例: ＣＰＵ１０、ＬＥＤ２５
      変数記号:    全角英字1文字 + (全角数字/半角英数字)* 例: Ｖ、ｔ、Ｖ０、Ｔmax

    戻り値: (drawing_pairs, variable_pairs)
      drawing_pairs:  [(要素名, 符号, offset), ...]  図面符号
      variable_pairs: [(物理量名, 変数記号, offset), ...]  変数記号
    """
    drawing_pairs  = []   # 図面符号ペア
    variable_pairs = []   # 変数記号ペア
    lines = text.splitlines(keepends=True)
    offset = 0

    for line in lines:
        # カギカッコ内をマスク（同じ文字数でオフセットを保持）
        masked = re.sub(r'「[^」]*」|『[^』]*』',
                         lambda m: '　' * len(m.group()), line)
        tokens = _tokenize(masked)
        for t in tokens:
            t['start'] += offset
            t['end']   += offset

        i = 0
        n = len(tokens)
        while i < n:
            t = tokens[i]

            # 形式名詞（とき・ため・うち等）はスキャン開始点にしない
            if _is_noun_tok(t) and not _is_fugo_tok(t) and _is_formal_noun_tok(t):
                i += 1
                continue

            # ── 変数記号スキャン ──────────────────────────────
            # 全角英字1文字トークン（単独または添字付き）で要素名が直前にある場合
            if (_is_zenkaku_alpha(t['surf'][0]) if t['surf'] else False) and len(t['surf']) == 1:
                # 直前トークンが全角数字列なら単位（１０ｍ等）としてスキップ
                prev_surf = tokens[i-1]['surf'] if i > 0 else ''
                prev_is_digit = (i > 0 and
                    all(_is_zenkaku_digit(c) for c in prev_surf) and len(prev_surf) >= 1)
                if not prev_is_digit:
                    # 変数記号本体を組み立て（全角英字1文字 + 全角数字 or 半角英数字の連続）
                    var_parts = [t['surf']]
                    k = i + 1
                    while k < n:
                        ns = tokens[k]['surf']
                        if (all(_is_zenkaku_digit(c) for c in ns) or
                                (ns.isascii() and ns.replace('_','').isalnum() and len(ns) <= 4)):
                            var_parts.append(ns)
                            k += 1
                        else:
                            break
                    var_sym = ''.join(var_parts)
                    # classify_fugo で変数記号と確認
                    if classify_fugo(var_sym) == 'variable':
                        # 直前の名詞列を物理量名として取得
                        # 形式名詞（ため・とき等）は物理量名に含めない（品詞ルール）
                        j2 = i - 1
                        phys_parts = []
                        while j2 >= 0 and _is_noun_tok(tokens[j2]) and tokens[j2]['pos1'] != '数詞':
                            if _is_formal_noun_tok(tokens[j2]):
                                break  # 形式名詞で区切る
                            surf = tokens[j2]['surf']
                            phys_parts.insert(0, surf)
                            j2 -= 1
                        # 形容詞語幹 + 名詞的接尾辞（深さ・高さ・長さ等）の取り込み
                        # 「さ/み/げ」等の接尾辞/名詞的 の直前が形容詞の場合、形容詞語幹も含める
                        if (phys_parts and j2 >= 0
                                and tokens[j2]['pos'] == '形容詞'
                                and len(phys_parts) >= 1
                                and tokens[j2 + 1]['pos'] == '接尾辞'
                                and tokens[j2 + 1]['pos1'] == '名詞的'):
                            phys_parts.insert(0, tokens[j2]['surf'])
                            j2 -= 1
                        phys = ''.join(phys_parts)
                        # 除外チェック（品詞ルール＋残留リスト）
                        phys_toks = _tokenize(phys) if phys else []
                        bad = (not phys or _is_fugo_exclude(phys, phys_toks))
                        if not bad:
                            char_off = tokens[i]['start']
                            variable_pairs.append((phys, var_sym, char_off))
                        i = k
                        continue

            # ── 図面符号スキャン ──────────────────────────────
            # 序列修飾の先行検出: 通常収集では拾えないパターンを先に処理
            #   「第１センサ１０」: 第(接頭辞)→１(fugo)→センサ→１０
            #   「一方のセンサ１０」: 一方→の→センサ→１０
            _ordinal_handled = False
            if _is_noun_tok(t) and not _is_fugo_tok(t):
                # 「第」接頭辞 + 数詞(fugo) + 名詞列 + 符号
                if (t['pos'] == '接頭辞' and t['surf'] == '第'
                        and i+1 < n and _is_fugo_tok(tokens[i+1])):
                    oj = i + 2
                    while (oj < n and _is_noun_tok(tokens[oj])
                           and not _is_fugo_tok(tokens[oj])
                           and tokens[oj]['surf'] not in _ZENSHOU_WORDS
                           and tokens[oj]['pos'] != '接尾辞'):
                        oj += 1
                    if oj < n and _is_fugo_tok(tokens[oj]) and oj > i+2:
                        o_name = ''.join(tok['surf'] for tok in tokens[i:oj])
                        o_core = ''.join(tok['surf'] for tok in tokens[i+2:oj])
                        if len(o_core) >= 2:
                            ofp, oj = _collect_fugo_suffix(tokens, oj)
                            o_fugo = ''.join(ofp)
                            if classify_fugo(o_fugo) == 'drawing':
                                drawing_pairs.append((o_name, o_fugo, tokens[i]['start'], o_core, 'ordinal'))
                                i = oj
                                _ordinal_handled = True
                # 「一方/他方」+ 'の' + 名詞列 + 符号
                elif (t['surf'] in _ORDINAL_MODS
                        and i+1 < n and tokens[i+1]['surf'] == 'の'):
                    oj = i + 2
                    while (oj < n and _is_noun_tok(tokens[oj])
                           and not _is_fugo_tok(tokens[oj])
                           and tokens[oj]['surf'] not in _ZENSHOU_WORDS
                           and tokens[oj]['pos'] != '接尾辞'):
                        oj += 1
                    if oj < n and _is_fugo_tok(tokens[oj]) and oj > i+2:
                        o_core = ''.join(tok['surf'] for tok in tokens[i+2:oj])
                        o_name = t['surf'] + 'の' + o_core
                        if len(o_core) >= 2:
                            ofp, oj = _collect_fugo_suffix(tokens, oj)
                            o_fugo = ''.join(ofp)
                            if classify_fugo(o_fugo) == 'drawing':
                                drawing_pairs.append((o_name, o_fugo, tokens[i]['start'], o_core, 'ordinal'))
                                i = oj
                                _ordinal_handled = True

            # パターン(A): 非fugo名詞列 → 全角数詞
            if not _ordinal_handled and _is_noun_tok(t) and not _is_fugo_tok(t):
                # 直前が図面符号トークンはスキップ
                if i > 0 and _is_fugo_tok(tokens[i-1]):
                    i += 1
                    continue
                # 接尾辞（ら・等・的）はスキャン開始点にしない
                if t['pos'] == '接尾辞':
                    i += 1
                    continue
                # 汎用修飾語+の: 「システム推奨の運行経路案」「その他の経路案」等
                # 名詞列+'の'の後に名詞列+符号が続く場合、前半修飾語を除去してwarning
                _mod_handled = False
                _mj = i
                while (_mj < n and _is_noun_tok(tokens[_mj])
                       and not _is_fugo_tok(tokens[_mj])
                       and not _is_formal_noun_tok(tokens[_mj])
                       and tokens[_mj]['surf'] not in _ZENSHOU_WORDS
                       and tokens[_mj]['pos'] != '接尾辞'):
                    _mj += 1
                if (_mj < n and tokens[_mj]['surf'] == 'の'
                        and tokens[_mj]['pos'] == '助詞'
                        and _mj > i):  # 名詞列+'の'を確認
                    _mj2 = _mj + 1  # 'の'の次から核名詞列
                    while (_mj2 < n and _is_noun_tok(tokens[_mj2])
                           and not _is_fugo_tok(tokens[_mj2])
                           and not _is_formal_noun_tok(tokens[_mj2])
                           and tokens[_mj2]['surf'] not in _ZENSHOU_WORDS
                           and tokens[_mj2]['pos'] != '接尾辞'):
                        _mj2 += 1
                    if (_mj2 < n and _is_fugo_tok(tokens[_mj2])
                            and _mj2 > _mj + 1):  # 核名詞列が存在
                        _mod_name = ''.join(tok['surf'] for tok in tokens[i:_mj])
                        _core_name = ''.join(tok['surf'] for tok in tokens[_mj+1:_mj2])
                        if len(_core_name) >= 2 and _mod_name:
                            ofp, _mj2 = _collect_fugo_suffix(tokens, _mj2)
                            o_fugo = ''.join(ofp)
                            if classify_fugo(o_fugo) == 'drawing':
                                # 修飾語付きはwarning候補として登録（mod_kind='mod'）
                                drawing_pairs.append((_core_name, o_fugo,
                                    tokens[i]['start'], _core_name, 'mod'))
                                i = _mj2
                                _mod_handled = True
                if _mod_handled:
                    continue
                # 名詞列収集（_is_fugo_tokで止まる・接尾辞は含まない）
                # 形式名詞（とき・ため・うち等）は要素名の核ではないので停止
                j = i
                while (j < n and _is_noun_tok(tokens[j])
                       and not _is_fugo_tok(tokens[j])
                       and not _is_formal_noun_tok(tokens[j])
                       and tokens[j]['surf'] not in _ZENSHOU_WORDS
                       and tokens[j]['pos'] != '接尾辞'):
                    j += 1

                if j < n and _is_fugo_tok(tokens[j]):
                    noun_toks_raw = tokens[i:j]
                    # 量化/序列修飾語を正規化
                    noun_toks, mod_kind = _strip_quant_prefix(noun_toks_raw)
                    name = ''.join(tok['surf'] for tok in noun_toks)
                    # 量化修飾（各・複数等）: 核名詞が空になる場合はスキップ
                    if mod_kind == 'quant' and not name:
                        i = j + 1
                        continue
                    # 序列修飾（第N・一方等）: 元の修飾語付きフル名を保持しつつ
                    # core_name を記録してM4②の除外判定に使う
                    full_name = ''.join(tok['surf'] for tok in noun_toks_raw)
                    core_name = name  # quant除去後 or ordinal除去後の核名詞
                    if mod_kind == 'ordinal':
                        name = full_name  # 登録はフル名で行う
                    if not (_is_fugo_exclude(core_name, noun_toks)
                            or _is_koho_name(core_name)
                            or _is_koho_name_part(core_name)
                            or len(core_name) < 2):
                        fugo_parts, j = _collect_fugo_suffix(tokens, j)
                        fugo = ''.join(fugo_parts)
                        if classify_fugo(fugo) == 'drawing':
                            char_off = noun_toks[0]['start'] if noun_toks else (
                                noun_toks_raw[0]['start'] if noun_toks_raw else offset)
                            drawing_pairs.append((name, fugo, char_off, core_name, mod_kind))
                        i = j if j > i else i + 1
                        continue

                # パターン(B): 名詞列の末尾が全角英字2文字以上 + 直後が全角数詞
                # fugashiが「ＣＰＵ」を名詞として切り出すケース
                # 名詞列の末尾トークンが全角英字2文字以上かチェック
                if j > i:
                    last_tok = tokens[j-1]
                    alpha_run = last_tok['surf']
                    if (len(alpha_run) >= 2
                            and all(_is_zenkaku_alpha(c) for c in alpha_run)
                            and j < n and _is_fugo_tok(tokens[j])):
                        # ＣＰＵ１０ パターン: alpha_run=ＣＰＵ, 数字=１０
                        fugo_parts, j = _collect_fugo_suffix(tokens, j)
                        fugo = ''.join(fugo_parts)
                        if classify_fugo(fugo) == 'drawing':
                            # 要素名はalpha_runを除いた名詞列
                            pre_toks = tokens[i:tokens.index(last_tok, i)]
                            name = ''.join(tok['surf'] for tok in pre_toks) if pre_toks else alpha_run
                            if len(name) < 1:
                                name = alpha_run  # ＣＰＵ単体が要素名
                            char_off = tokens[i]['start']
                            core_name = name
                            mod_kind = None
                            drawing_pairs.append((name, fugo, char_off, core_name, mod_kind))
                            i = j
                            continue

            i += 1

        offset += len(line)
    return drawing_pairs, variable_pairs


def _offset_to_para_id(desc_text, char_offset):
    """文字オフセットから最も近い【XXXX】段落IDを返す"""
    para_pat = re.compile(r'【(\d{4})】')
    current = None
    for m in para_pat.finditer(desc_text):
        if m.start() <= char_offset:
            current = 'p-' + m.group(1)
        else:
            break
    return current


def _lineno_to_para_id(desc_text, lineno):
    """旧API互換：行番号→段落ID"""
    para_pat = re.compile(r'^【(\d{4})】', re.MULTILINE)
    current = None
    for i, line in enumerate(desc_text.splitlines(), 1):
        m = para_pat.match(line)
        if m:
            current = 'p-' + m.group(1)
        if i == lineno:
            return current
    return current


def check_fugo(claims, sections):
    """符号チェック（図面符号と変数記号）。"""
    issues = []
    # スコープ: 「発明を実施するための形態」（旧式含む）を優先して抽出
    # drawings（図面の簡単な説明）は符号登録源として含める
    _raw = sections.get("_raw", "")
    _desc_match = re.search(
        r'【(?:発明を実施するための(?:最良の)?形態|発明の実施の形態)】(.*?)(?=\n【[^】]+】)',
        _raw, re.DOTALL)
    desc_text = (_desc_match.group(1) if _desc_match
                 else sections.get("description", ""))
    desc_text += sections.get("drawings", "")
    claims_text = sections.get("claims", "")

    # 抽出: 図面符号ペアと変数記号ペアを分離
    drawing_pairs, variable_pairs = _extract_elements_tokens(desc_text)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 図面符号チェック
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    fugo_to_names = {}   # {fugo: {name: offset}}
    name_to_fugos = {}   # {name: {fugo: offset}}
    # core_name_map: 登録名 → 核名詞（序列修飾除去後）
    core_name_map  = {}  # {name: core_name}
    # ordinal_cores: 序列修飾語付きの核名詞セット（M4②の除外判定用）
    ordinal_cores  = {}  # {core_name: set of names}
    for row in drawing_pairs:
        name, fugo, off = row[0], row[1], row[2]
        core_name = row[3] if len(row) > 3 else name
        mod_kind  = row[4] if len(row) > 4 else None
        fugo_to_names.setdefault(fugo, {})[name] =             min(fugo_to_names.get(fugo, {}).get(name, off), off)
        name_to_fugos.setdefault(name, {})[fugo] =             min(name_to_fugos.get(name, {}).get(fugo, off), off)
        core_name_map[name] = core_name
        if mod_kind == 'ordinal':
            ordinal_cores.setdefault(core_name, set()).add(name)

    # ① 1符号 → 複数要素名（ERROR）
    for fugo, name_map in sorted(fugo_to_names.items()):
        if len(name_map) > 1:
            names = list(name_map.keys())
            issues.append({
                "milestone": "M4", "level": "error",
                "msg": (f"符号「{fugo}」に複数の要素名が対応しています：" +
                        "・".join(names) + "（誤記または表記ゆれの可能性）"),
                "detail": f"offset {list(name_map.values())}",
                "para_ids": [_offset_to_para_id(desc_text, off)
                             for off in name_map.values()],
            })

    # ② 1要素名 → 複数符号（WARNING）
    # 序列修飾語グループ（第N・一方/他方）の核名詞は除外
    for name, fugo_map in sorted(name_to_fugos.items()):
        if len(fugo_map) <= 1:
            continue
        core = core_name_map.get(name, name)
        # 序列修飾グループ内の要素名は「第１センサ→１０」「第２センサ→２０」が正常なため除外
        if core in ordinal_cores and name in ordinal_cores[core]:
            continue
        fugos = sorted(fugo_map.keys(), key=lambda f: z2h(f))
        def is_hierarchical(f1, f2):
            h1, h2 = z2h(f1), z2h(f2)
            return h2.startswith(h1) or h1.startswith(h2)
        non_hier = [(f1, f2) for i2, f1 in enumerate(fugos)
                    for f2 in fugos[i2+1:] if not is_hierarchical(f1, f2)]
        if non_hier:
            issues.append({
                "milestone": "M4", "level": "warning",
                "msg": (f"要素名「{name}」に複数の符号が対応しています：" +
                        "・".join(fugos) +
                        "（意図的な場合もありますが確認を推奨）"),
                "detail": f"offset {list(fugo_map.values())}",
                "para_ids": [_offset_to_para_id(desc_text, off)
                             for off in fugo_map.values()],
            })

    # ③ 請求項内の括弧付き符号（STYLE）
    CLAIM_FUGO_PAT = re.compile(
        r'[（(](?:[０-９]+[Ａ-Ｚａ-ｚ]*|[0-9]+[A-Za-z]*)[）)]')
    for m in CLAIM_FUGO_PAT.finditer(claims_text):
        pos = m.start()
        claim_num = "?"
        for mm in re.finditer(r'【請求項([０-９0-9]+)】', claims_text):
            if mm.start() <= pos:
                claim_num = z2h(mm.group(1))
        issues.append({
            "milestone": "M4", "level": "style",
            "msg": (f"請求項{claim_num}に符号「{m.group(0)}」が含まれています。"
                    f"請求項には符号を入れないスタイルを推奨します。"),
            "detail": "",
        })

    # ④ 半角数字の符号（STYLE）
    seen_half = set()
    for line_no, line in enumerate(desc_text.splitlines(), 1):
        tokens = _tokenize(line)
        for i2, t in enumerate(tokens):
            if not _is_half_digit(t['surf']) or t['pos1'] != '数詞':
                continue
            j2 = i2 - 1
            name_parts = []
            while j2 >= 0 and _is_noun_tok(tokens[j2]) and tokens[j2]['pos1'] != '数詞':
                name_parts.insert(0, tokens[j2]['surf'])
                j2 -= 1
            name = ''.join(name_parts)
            if len(name) < 2:
                continue
            key = (name, t['surf'])
            if key in seen_half:
                continue
            seen_half.add(key)
            issues.append({
                "milestone": "M4", "level": "style",
                "msg": (f"半角数字の符号が使用されています：「{name}{t['surf']}」。"
                        f"全角数字への統一を推奨します。"),
                "detail": f"行{line_no}：{line.strip()[:40]}",
                "para_ids": [_lineno_to_para_id(desc_text, line_no)],
            })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 変数記号チェック
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    vsym_to_phys = {}   # {変数記号: {物理量名: offset}}
    phys_to_vsym = {}   # {物理量名: {変数記号: offset}}
    for phys, vsym, off in variable_pairs:
        if not phys:
            continue
        vsym_to_phys.setdefault(vsym, {})[phys] =             min(vsym_to_phys.get(vsym, {}).get(phys, off), off)
        phys_to_vsym.setdefault(phys, {})[vsym] =             min(phys_to_vsym.get(phys, {}).get(vsym, off), off)

    # ⑤ 1変数記号 → 複数物理量名（INFO: 意味の衝突の可能性）
    for vsym, phys_map in sorted(vsym_to_phys.items()):
        if len(phys_map) > 1:
            physnames = list(phys_map.keys())
            issues.append({
                "milestone": "M4", "level": "info",
                "msg": (f"変数記号「{vsym}」に複数の物理量名が対応しています：" +
                        "・".join(physnames) + "（意味の衝突の可能性）"),
                "detail": "",
                "para_ids": [_offset_to_para_id(desc_text, off)
                             for off in phys_map.values()],
            })

    # テーブル生成
    all_names = sorted({row[0] for row in drawing_pairs})
    element_table = [
        {"name": name, "fugos": sorted(name_to_fugos.get(name, {}).keys())}
        for name in all_names
    ]
    fugo_count = Counter(row[1] for row in drawing_pairs)
    fugo_table = [
        {
            "fugo":   fugo,
            "names":  sorted(fugo_to_names[fugo].keys()),
            "count":  fugo_count[fugo],
            "is_dup": len(fugo_to_names[fugo]) > 1,
        }
        for fugo in sorted(fugo_to_names.keys())
    ]
    # 変数記号テーブル
    var_table = [
        {
            "vsym":    vsym,
            "physnames": sorted(vsym_to_phys[vsym].keys()),
            "count":   sum(1 for _, v, _ in variable_pairs if v == vsym),
            "is_dup":  len(vsym_to_phys[vsym]) > 1,
        }
        for vsym in sorted(vsym_to_phys.keys())
    ]

    return issues, element_table, fugo_table, var_table


# ══════════════════════════════════════════════════════════
# JIS X 0208 文字コードチェック
# ══════════════════════════════════════════════════════════

def _jis_char_status(char):
    """1文字のJIS X 0208適合状況を返す。
    戻り値: ('ok', reason) | ('ng', reason) | ('warn', reason) | ('skip', reason)
    'skip' は改ページ等の制御文字（別途処理するため個別検出対象外）
    """
    cp = ord(char)
    # 改行・タブ等の通常制御文字はスキップ（check_jis側で除外済み）
    if cp in (0x09, 0x0A, 0x0D):  # TAB, LF, CR
        return 'skip', '改行/タブ'
    # 改ページ (Form Feed): Wordからの変換で混入する可能性あり
    if cp == 0x0C:
        return 'warn', '改ページ文字（FF, U+000C）が含まれています。出願前に削除または改行に変換を推奨します。'
    # その他の制御文字 (0x00-0x1F, 0x7F)
    if cp < 0x20 or cp == 0x7F:
        return 'ng', f'制御文字（U+{cp:04X}）'

    try:
        encoded = char.encode('cp932')
    except UnicodeEncodeError:
        return 'ng', 'Shift_JIS変換不可'

    if len(encoded) == 1:
        b = encoded[0]
        if 0x20 <= b <= 0x7E:
            return 'ok', 'ASCII'
        if 0xA1 <= b <= 0xDF:
            return 'warn', '半角カタカナ（全角推奨）'
        return 'ng', f'不明な1バイト文字'

    if len(encoded) == 2:
        b1, b2 = encoded[0], encoded[1]
        # NEC特殊文字: 0x8740-0x879C（ローマ数字・丸数字・単位合字等）
        if b1 == 0x87 and 0x40 <= b2 <= 0x9C:
            return 'ng', 'NEC特殊文字（JIS X 0208外）'
        # NEC選定IBM拡張: 0xED40-0xEEFC（異体字等）
        if 0xED <= b1 <= 0xEE:
            return 'ng', 'NEC選定IBM拡張文字（JIS X 0208外）'
        # IBM拡張文字: 0xFA40-0xFC4B
        if 0xFA <= b1 <= 0xFC:
            return 'ng', 'IBM拡張文字（JIS X 0208外）'
        # 通常のShift_JIS（JIS X 0208範囲）
        return 'ok', 'JIS X 0208'

    return 'ng', '変換エラー'


# 代替文字の提案テーブル
_JIS_ALTERNATIVES = {
    'Ⅰ': 'I（半角）またはI（全角）',
    'Ⅱ': 'II（半角）またはII（全角）',
    'Ⅲ': 'III（半角）またはIII（全角）',
    'Ⅳ': 'IV（半角）またはIV（全角）',
    'Ⅴ': 'V（半角）またはV（全角）',
    'Ⅵ': 'VI（半角）',
    'Ⅶ': 'VII（半角）',
    'Ⅷ': 'VIII（半角）',
    'Ⅸ': 'IX（半角）',
    'Ⅹ': 'X（半角）',
    '①': '(1)などに変更',
    '②': '(2)などに変更',
    '③': '(3)などに変更',
    '④': '(4)などに変更',
    '⑤': '(5)などに変更',
    '⑥': '(6)などに変更',
    '⑦': '(7)などに変更',
    '⑧': '(8)などに変更',
    '⑨': '(9)などに変更',
    '⑩': '(10)などに変更',
    '㈱': '(株)に変更',
    '㌔': 'キロ またはkg等に変更',
    '㍉': 'ミリ またはmm等に変更',
    '㌃': 'アール またはa等に変更',
    '∑': 'Σ（全角Σはcp932で使用可能）',
}


def _section_label(sec_key):
    """セクションキーを日本語ラベルに変換"""
    return {
        'title': '発明の名称',
        'claims': '特許請求の範囲',
        'description': '発明の詳細な説明',
        'drawings': '図面の簡単な説明',
        'abstract': '要約',
        '_raw': '文書全体',
    }.get(sec_key, sec_key)


def check_jis(sections):
    """全セクションをスキャンしてJIS X 0208外文字を検出する。"""
    issues = []
    seen_ng   = {}  # {char: (section_label, lineno, context)}  重複排除
    seen_warn = {}

    for sec_key in ('title', 'claims', 'description', 'drawings', 'abstract', '_raw'):
        text = sections.get(sec_key, '')
        if not text:
            continue
        label = _section_label(sec_key)
        # 改ページ(\x0c)はsplitlines()で行区切りになるため事前に検出
        if '\x0c' in text:
            ff_line = next(
                (i+1 for i, l in enumerate(text.splitlines()) if '\x0c' in l), 1
            )
            context = text.splitlines()[ff_line-1].strip()[:40] if text.splitlines() else ''
            key = (sec_key, '\x0c')
            if key not in seen_warn:
                seen_warn[key] = (label, ff_line, context,
                    '改ページ文字（FF, U+000C）が含まれています。出願前に削除または改行に変換を推奨します。',
                    'U+000C')
        for lineno, line in enumerate(text.splitlines(), 1):
            for col, char in enumerate(line, 1):
                if char in (' ', '\t', '\n', '\r'):
                    continue
                status, reason = _jis_char_status(char)
                if status == 'skip':
                    continue
                if status == 'ng':
                    key = char
                    if key not in seen_ng:
                        alt = _JIS_ALTERNATIVES.get(char, '')
                        context = line.strip()[:40]
                        # 不可視文字は文字コードで表示
                        cp = ord(char)
                        display = char if cp >= 0x20 else f'U+{cp:04X}'
                        seen_ng[key] = (label, lineno, context, reason, alt, display)
                elif status == 'warn':
                    key = (sec_key, char)
                    if key not in seen_warn:
                        context = line.strip()[:40]
                        cp = ord(char)
                        display = char if cp >= 0x20 else f'U+{cp:04X}'
                        seen_warn[key] = (label, lineno, context, reason, display)

    for char, (sec_label, lineno, context, reason, alt, display) in sorted(
            seen_ng.items(), key=lambda x: ord(x[0])):
        alt_str = f'　→ {alt}' if alt else ''
        cp = ord(char)
        cp_str = f' (U+{cp:04X})' if cp < 0x20 or not char.isprintable() else ''
        issues.append({
            'milestone': 'M5',
            'level': 'warning',
            'msg': f'JIS外文字「{display}」{cp_str}が使用されています（{reason}）{alt_str}',
            'detail': f'{sec_label} 行{lineno}付近：{context}',
        })

    for (sec_key, char), (sec_label, lineno, context, reason, display) in sorted(
            seen_warn.items(), key=lambda x: x[0]):
        cp = ord(char) if len(char) == 1 else 0
        is_ctrl = (cp > 0 and cp < 0x20)
        issues.append({
            'milestone': 'M5',
            'level': 'warning' if is_ctrl else 'style',
            'msg': (f'「{display}」{reason}' if is_ctrl
                    else f'「{display}」は{reason}'),
            'detail': f'{sec_label} 行{lineno}付近：{context}',
        })

    return issues


# ══════════════════════════════════════════════════════════
# 記録項目・段落番号・句点チェック
# ══════════════════════════════════════════════════════════

# TYPE1: 右側に記述が必要（段落番号チェック対象外）
_HEADING_TYPE1 = {
    '書類名', '発明の名称', '整理番号', '提出日', 'あて先',
    '国際特許分類', '住所又は居所', '氏名又は名称', '識別番号', '予納台帳番号',
}

# TYPE2: 右側不要・配下に段落番号が必要
_HEADING_TYPE2 = {
    '技術分野', '背景技術',
    '特許文献',      # 先行技術文献グループ内（直接内容を持つ場合もある）
    '非特許文献',
    '発明が解決しようとする課題',
    '課題を解決するための手段',
    '発明の効果',
    '発明を実施するための形態',
    '発明を実施するための最良の形態',  # 旧式（2011年以前）
    '発明の実施の形態',              # 旧式2（2002年以前）
    '産業上の利用可能性',
}

# TYPE2_NOCHECK: 段落番号チェックを行わないセクション
_HEADING_TYPE2_NOCHECK = {
    '図面の簡単な説明',
    '符号の説明',
    '要約',
    '要約書',
}

# TYPE3: 右側不要・配下に段落番号不要（次に決まった見出しが来る）
_HEADING_TYPE3 = {
    '先行技術文献',  # 直下に特許文献/非特許文献が来る
    '発明の概要',   # 直下に課題・手段・効果が来る
    '特許請求の範囲',  # 配下は【請求項N】形式
}

# TYPE4: 直前に段落番号が必要（数N・表N・化N）
_HEADING_TYPE4_PAT = re.compile(r'^(数|表|化)[０-９0-9]+$')


def _heading_type(label):
    """見出しラベルを4分類で返す"""
    if label in _HEADING_TYPE1:
        return 1
    if label in _HEADING_TYPE2_NOCHECK:
        return 1  # 段落番号チェック不要として扱う
    if label in _HEADING_TYPE2:
        return 2
    if re.match(r'^実施例[０-９0-9]*$', label):
        return 2  # 実施例N
    if label in _HEADING_TYPE3:
        return 3
    if _HEADING_TYPE4_PAT.match(label):
        return 4
    if re.match(r'^(特許文献|非特許文献)[０-９0-9]+$', label):
        return 1  # 右側に文献情報を記述
    return 2  # その他（不明な見出し）→ TYPE2として扱う


_MEISHO_ITEMS = [
    ('技術分野',        '【技術分野】',                       'optional'),
    ('背景技術',        '【背景技術】',                       'optional'),
    ('先行技術文献',    '【先行技術文献】',                   'optional'),
    ('特許文献',        '【特許文献】',                       'conditional'),
    ('非特許文献',      '【非特許文献】',                     'conditional'),
    ('発明の概要',      '【発明の概要】',                     'optional'),
    ('発明の課題',      '【発明が解決しようとする課題】',     'optional'),
    ('課題の手段',      '【課題を解決するための手段】',       'optional'),
    ('発明の効果',      '【発明の効果】',                     'optional'),
    ('図面の説明',      '【図面の簡単な説明】',               'conditional'),
    ('実施形態',        '【発明を実施するための形態】',       'optional'),
    ('産業上の利用',    '【産業上の利用可能性】',             'optional'),
    ('符号の説明',      '【符号の説明】',                     'optional'),
]

# 段落番号を挟まずに隣接できる見出しペア（親→子）
_NO_PARA_BETWEEN = {
    ('先行技術文献', '特許文献'),
    ('先行技術文献', '非特許文献'),
    ('特許文献', '非特許文献'),
    ('発明の概要', '発明が解決しようとする課題'),
    ('発明の概要', '課題を解決するための手段'),
    ('発明の概要', '発明の効果'),
}


def check_structure(text):
    """記録項目の存在・順序・段落番号配置をチェック。
    J-PlatPat公報固有ヘッダを除外するため、
    【発明の詳細な説明】または【特許請求の範囲】以降の行のみを対象とする。
    """
    issues = []
    lines = text.splitlines()

    # 明細書本文の開始行を特定
    start_line = 0
    for i, line in enumerate(lines):
        if re.search(r'【発明の詳細な説明】|【特許請求の範囲】', line):
            start_line = i
            break
    lines = lines[start_line:]

    # 見出し行を抽出: (lineno, label)
    headings = []
    for i, line in enumerate(lines):
        m = re.match(r'^【([^】\d０-９]+)】\s*$', line.strip())
        if m:
            headings.append((i+1, m.group(1), line.strip()))

    heading_labels = [h[1] for h in headings]

    # ── 必須項目の欠落チェック ──
    text_for_check = '\n'.join(lines)
    for key, label, req in _MEISHO_ITEMS:
        label_bare = label.strip('【】')
        # 見出し単独行 または インライン（同行に値あり）の両方で存在確認
        present = (any(h == label_bare for h in heading_labels) or
                   re.search(re.escape(label), text_for_check) is not None)
        if not present:
            if req == 'required':
                issues.append({
                    'milestone': 'M5', 'level': 'error',
                    'msg': f'必須項目 {label} がありません',
                })
            elif req == 'conditional':
                issues.append({
                    'milestone': 'M5', 'level': 'info',
                    'msg': f'項目 {label} がありません（条件必須：該当する場合は記載が必要です）',
                })

    # ── 項目の出現順序チェック ──
    defined_order = [label.strip('【】') for _, label, _ in _MEISHO_ITEMS]
    present_in_order = [h for h in heading_labels if h in defined_order]
    sorted_by_rule = sorted(present_in_order, key=lambda h: defined_order.index(h)
                            if h in defined_order else 999)
    if present_in_order != sorted_by_rule:
        for i, (actual, expected) in enumerate(zip(present_in_order, sorted_by_rule)):
            if actual != expected:
                issues.append({
                    'milestone': 'M5', 'level': 'warning',
                    'msg': f'項目順序の異常：【{actual}】の位置に【{expected}】が期待されます',
                    'detail': f'現在の順序：{" → ".join(present_in_order)}',
                })
                break  # 最初の逸脱のみ報告

    # ── 同一項目の重複チェック ──
    seen_headings = {}
    for lineno, label, _ in headings:
        if label in seen_headings:
            issues.append({
                'milestone': 'M5', 'level': 'warning',
                'msg': f'項目【{label}】が重複しています（行{seen_headings[label]}と行{lineno}）',
            })
        else:
            seen_headings[label] = lineno

    # ── 段落番号の配置チェック（4分類に基づく） ──
    para_pat = re.compile(r'^【\d{4,5}】')

    # 旧式の見出し確認
    for _roushiki_label, _roushiki_since in [
        ('発明を実施するための最良の形態', '2011年以降'),
        ('発明の実施の形態', '2002年以降'),
    ]:
        if any(h == _roushiki_label for h in heading_labels):
            issues.append({
                'milestone': 'M5', 'level': 'info',
                'msg': f'【{_roushiki_label}】（旧式）が使用されています。'
                       f'{_roushiki_since}の出願では【発明を実施するための形態】が標準です。',
            })

    for idx, (lineno, label, _) in enumerate(headings):
        htype = _heading_type(label)
        next_heading_line = headings[idx+1][0] if idx+1 < len(headings) else len(lines)+1
        block_lines = lines[lineno:next_heading_line-1]
        has_content = any(l.strip() for l in block_lines)

        if htype == 1:
            # TYPE1: 右側に記述が必要 → 段落番号チェック不要
            continue
        elif htype == 3:
            # TYPE3: 段落番号不要（次の見出しが来ることを期待）
            # 段落番号が混入していたら警告
            has_para = any(para_pat.match(l.strip()) for l in block_lines)
            if has_para and has_content:
                issues.append({
                    'milestone': 'M5', 'level': 'info',
                    'msg': f'【{label}】の直下に段落番号があります（通常は次の見出しのみが来ます）',
                    'detail': f'行{lineno}',
                })
            continue
        elif htype == 4:
            # TYPE4: 直前に段落番号が必要 → 直前チェック（現状は省略）
            continue
        else:
            # TYPE2: 配下に段落番号が必要
            has_para = any(para_pat.match(l.strip()) for l in block_lines)
            # 次の見出しとの間がTYPE3的なペアならスキップ
            next_label = headings[idx+1][1] if idx+1 < len(headings) else None
            if next_label and (label, next_label) in _NO_PARA_BETWEEN:
                continue
            if not has_para and has_content:
                issues.append({
                    'milestone': 'M5', 'level': 'warning',
                    'msg': f'【{label}】の配下に段落番号がありません',
                    'detail': f'行{lineno}：内容を記録する場合は段落番号が必要です',
                })

    return issues


def check_para_nums(text):
    """段落番号【XXXX】の連続性（欠番・重複・逆転）をチェック。"""
    issues = []

    # 全段落番号を行番号付きで抽出
    # 要約・要約書セクションは別途番号体系を持つため除外する
    _abstract_start = re.compile(r'^【(?:要約書?|ABSTRACT)】', re.IGNORECASE)
    _abstract_end = re.compile(r'^【(?:発明の詳細な説明|特許請求の範囲|図面の簡単な説明)】')
    in_abstract = False
    entries = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if _abstract_start.match(stripped):
            in_abstract = True
        elif in_abstract and _abstract_end.match(stripped):
            in_abstract = False
        if in_abstract:
            continue
        m = re.match(r'^【(\d{4,5})】', stripped)
        if m:
            entries.append((i, int(m.group(1))))

    if not entries:
        return issues

    seen = {}
    for lineno, num in entries:
        if num in seen:
            issues.append({
                'milestone': 'M5', 'level': 'warning',
                'msg': f'段落番号【{num:04d}】が重複しています（行{seen[num]}と行{lineno}）',
            })
        seen[num] = lineno

    nums = [n for _, n in entries]
    for i in range(1, len(nums)):
        prev, curr = nums[i-1], nums[i]
        if curr < prev:
            issues.append({
                'milestone': 'M5', 'level': 'warning',
                'msg': f'段落番号が逆転しています：【{prev:04d}】→【{curr:04d}】',
                'detail': f'行{entries[i][0]}付近',
            })
        elif curr > prev + 1:
            missing = list(range(prev+1, curr))
            miss_str = '、'.join(f'【{n:04d}】' for n in missing[:5])
            if len(missing) > 5:
                miss_str += f'…（計{len(missing)}件）'
            issues.append({
                'milestone': 'M5', 'level': 'warning',
                'msg': f'段落番号に欠番があります：{miss_str}',
                'detail': f'【{prev:04d}】（行{entries[i-1][0]}）→【{curr:04d}】（行{entries[i][0]}）',
            })

    return issues


# 句点不要とみなす行のパターン
_KUTEN_EXEMPT_PATS = [
    re.compile(r'^【'),                          # 【セクション名】【段落番号】等
    re.compile(r'^[０-９\d]+[．.]'),             # 「１．構成」等の章番号
    re.compile(r'^（[０-９\d一二三四五六七八九十あいうえおかきくけこ]+）'),  # （１）（あ）等
    re.compile(r'^[一二三四五六七八九十]+[、．]'), # 「一、」「二．」等
    re.compile(r'^[(（][０-９\d]+[)）]'),         # (1) （１） 等
    re.compile(r'^[・•]'),                       # 箇条書き
    re.compile(r'[＝=＋\-×÷≠≒≦≧∈∉∞√∫∑∂]'),   # 数式・化学式行
    re.compile(r'^[A-Za-zＡ-Ｚａ-ｚ０-９\d]+\s*[＝=]'),  # 変数定義式
]


def _is_kuten_exempt(line):
    """句点なしを許容する行か判定。"""
    s = line.strip()
    if not s or len(s) <= 1:
        return True
    for pat in _KUTEN_EXEMPT_PATS:
        if pat.search(s):
            return True
    return False


def check_kuten(sections):
    """詳細説明・請求の範囲で句点なしの文末を検出。"""
    issues = []
    # 対象: 発明の詳細な説明のみ（請求項は parse_claims で個別チェック済み）
    for sec_key in ('description',):
        text = sections.get(sec_key, '')
        if not text:
            continue
        lines = text.splitlines()
        # 段落ブロックを構築: 【XXXX】で区切られた段落内の末尾行を確認
        para_start = None
        para_lines = []
        in_fugo_section = False  # 符号の説明セクション内は句点不要

        def flush_para(plines, start_lineno):
            """段落末尾の句点チェック。段落全体を1文として扱う。"""
            # 段落内の最後の非空行
            last = None
            for l in reversed(plines):
                if l.strip():
                    last = l.strip()
                    break
            if last is None:
                return None
            if _is_kuten_exempt(last):
                return None
            if last.endswith('。') or last.endswith('」') or last.endswith('）'):
                return None
            # 「。」が段落内のどこかにあれば文末句点ありとみなす
            full = ' '.join(l.strip() for l in plines if l.strip())
            if '。' in full:
                return None
            return {
                'milestone': 'M5', 'level': 'info',
                'msg': f'句点「。」で終わっていない段落があります',
                'detail': f'行{start_lineno}付近：{last[:40]}',
            }

        para_pat = re.compile(r'^【(\d{4,5})】')
        _fugo_heading = re.compile(r'^【符号の説明】')
        _next_heading = re.compile(r'^【[^０-９0-9][^】]*】')  # 次の見出し（段落番号以外）
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 符号の説明セクションの開始を検出
            if _fugo_heading.match(stripped):
                if para_lines:
                    if not in_fugo_section:
                        iss = flush_para(para_lines, para_start)
                        if iss:
                            issues.append(iss)
                    para_lines = []
                in_fugo_section = True
                para_start = None
                continue
            # 符号の説明の後に別の見出しが来たら通常モードに戻る
            if in_fugo_section and _next_heading.match(stripped):
                in_fugo_section = False
            if para_pat.match(stripped):
                if para_lines and not in_fugo_section:
                    iss = flush_para(para_lines, para_start)
                    if iss:
                        issues.append(iss)
                if not in_fugo_section:
                    para_start = i
                    para_lines = [line]
                else:
                    para_start = None
                    para_lines = []
            elif para_start is not None and not in_fugo_section:
                para_lines.append(line)
        if para_lines and not in_fugo_section:
            iss = flush_para(para_lines, para_start)
            if iss:
                issues.append(iss)

    return issues


# ══════════════════════════════════════════════════════════
# 要約チェック（400字・項目）
# ══════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════
# 符号の説明セクション照合（M4強化）
# ══════════════════════════════════════════════════════════

def _parse_fugo_setsumeisho(text):
    """【符号の説明】セクションのテキストから (符号, 名称) ペアを抽出。
    対応形式:
      ① 符号…名称、符号…名称  （全角三点リーダ区切り）
      ② 符号　名称\n           （タブ/全角スペース区切り・改行）
      ③ 符号 名称\n            （半角スペース区切り）
    """
    pairs = {}   # {符号: 名称}
    # 段落番号行を除去
    body = re.sub(r'【\d{4,5}】', '', text)

    # パターン①: 符号…名称（全角三点リーダまたは…）
    for m in re.finditer(
            r'([\uff10-\uff19][\uff10-\uff19a-zA-Z\uff41-\uff5a\uff21-\uff3a\uff0d]*)'
            r'[\u2026\u2025\u30fb\-\uff0d]+'
            r'([^\u3001\uff0c,\r\n\u3010\u3011\uff10-\uff190-9]{1,30})',
            body):
        fugo = m.group(1).strip()
        name = m.group(2).strip().rstrip('、，,')
        if fugo and name:
            pairs[fugo] = name

    # パターン②③: 符号[スペース/タブ]名称（行単位）
    if not pairs:
        for line in body.splitlines():
            line = line.strip()
            m2 = re.match(
                r'^([０-９０-９][０-９０-９a-zA-Zａ-ｚＡ-Ｚ－]*)'
                r'[\s　	]+(.+)$',
                line)
            if m2:
                fugo = m2.group(1).strip()
                name = m2.group(2).strip()
                if fugo and name:
                    pairs[fugo] = name

    return pairs


def check_fugo_setsumeisho(fugo_table, text):
    """明細書本文の符号テーブルと【符号の説明】セクションを照合。
    fugo_table: check_fugoが返す [{fugo, names, count, is_dup}, ...]
    """
    issues = []

    # 【符号の説明】を抽出
    m = re.search(r'【符号の説明】(.*?)(?=\n【[^】\d][^】]*】|\Z)', text, re.DOTALL)
    if not m:
        issues.append({
            'milestone': 'M4', 'level': 'info',
            'msg': '【符号の説明】セクションが見つかりません',
            'detail': '図面がある場合は符号の説明を記載することが推奨されます',
        })
        return issues, {}

    setsu_pairs = _parse_fugo_setsumeisho(m.group(1))
    if not setsu_pairs:
        issues.append({
            'milestone': 'M4', 'level': 'info',
            'msg': '【符号の説明】の符号エントリを読み取れませんでした',
        })
        return issues, setsu_pairs

    # 本文符号セット
    body_fugos = {row['fugo']: row['names'] for row in fugo_table}

    # ① 本文にあって説明にない符号
    for fugo, names in sorted(body_fugos.items()):
        if fugo not in setsu_pairs:
            issues.append({
                'milestone': 'M4', 'level': 'warning',
                'msg': f'符号「{fugo}」（{"/".join(names)}）が【符号の説明】にありません',
            })

    # ② 説明にあって本文にない符号
    for fugo, name in sorted(setsu_pairs.items()):
        if fugo not in body_fugos:
            issues.append({
                'milestone': 'M4', 'level': 'info',
                'msg': f'【符号の説明】の「{fugo}　{name}」が明細書本文で使用されていません',
            })

    # ③ 両方にあるが名称が不一致
    for fugo in sorted(set(body_fugos) & set(setsu_pairs)):
        body_names = body_fugos[fugo]
        setsu_name = setsu_pairs[fugo]
        # 説明の名称が本文の要素名のいずれとも一致しない場合
        if not any(setsu_name in bn or bn in setsu_name for bn in body_names):
            issues.append({
                'milestone': 'M4', 'level': 'warning',
                'msg': (f'符号「{fugo}」の名称が不一致：'
                        f'本文「{"/".join(body_names)}」⇔説明「{setsu_name}」'),
            })

    return issues, setsu_pairs


# ══════════════════════════════════════════════════════════
# 見出しナンバー順序チェック
# ══════════════════════════════════════════════════════════

def check_midashi_numbers(sections):
    """発明の詳細な説明内の見出しナンバー（１．…、（１）…等）の順序をチェック。"""
    issues = []
    text = sections.get('description', '')
    if not text:
        return issues

    # パターン: 全角数字＋「．」 または （全角数字）
    # 階層: レベル1=「１．」, レベル2=「（１）」
    level1_pat = re.compile(r'^[　\s]*([１-９１-９][０-９０-９]*)[\．.]')
    level2_pat = re.compile(r'^[　\s]*（([１-９１-９][０-９０-９]*)）')

    def zenkaku_to_int(s):
        return int(s.translate(str.maketrans('０１２３４５６７８９','0123456789')))

    prev1 = 0
    prev2 = 0
    in_para = False  # 【XXXX】段落内かどうか

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if re.match(r'^【\d{4,5}】', stripped):
            in_para = True
            prev2 = 0  # 段落が変わったらレベル2リセット
            continue

        m1 = level1_pat.match(stripped)
        if m1:
            n = zenkaku_to_int(m1.group(1))
            if n != prev1 + 1 and prev1 > 0:
                issues.append({
                    'milestone': 'M5', 'level': 'info',
                    'msg': (f'見出しナンバー「{m1.group(1)}．」の順序異常'
                            f'（前回：{prev1}、今回：{n}、行{lineno}）'),
                })
            prev1 = n
            prev2 = 0
            continue

        m2 = level2_pat.match(stripped)
        if m2:
            n = zenkaku_to_int(m2.group(1))
            if n != prev2 + 1 and prev2 > 0:
                issues.append({
                    'milestone': 'M5', 'level': 'info',
                    'msg': (f'見出しナンバー「（{m2.group(1)}）」の順序異常'
                            f'（前回：{prev2}、今回：{n}、行{lineno}）'),
                })
            prev2 = n

    return issues


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


# ══════════════════════════════════════════════════════════
# M6: サポート要件チェック
# ══════════════════════════════════════════════════════════

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
    # → STOP_WORDSのみ確認して有効と判定
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


def extract_nouns_for_support(text):
    """サポート要件チェック用の名詞抽出。品詞ベースフィルタで不適切語句を除去。"""
    # 照応詞・「請求項N」を除去してから名詞句を収集
    clean = re.sub(r'前記|上記|当該|該', '', text)
    clean = re.sub(r'請求項[０-９0-9一二三四五六七八九十１-９]+', '', clean)
    raw_nouns = extract_defined_nouns(clean)
    # 品詞ベースフィルタ
    nouns = {n for n in raw_nouns if _is_valid_support_noun(n)}
    # 包含除去：別の語句に完全に含まれる短い語は削除
    sorted_nouns = sorted(nouns, key=len, reverse=True)
    keep = []
    for noun in sorted_nouns:
        if not any(noun in longer for longer in keep):
            keep.append(noun)
    return set(keep)


def _extract_section_text(desc, *headers):
    """descriptionから指定見出しのセクションテキストを結合して返す"""
    result = []
    for header in headers:
        m = re.search(r'【' + re.escape(header) + r'】([\s\S]*?)(?=【[^０-９\d]|$)', desc)
        if m:
            result.append(m.group(1))
    return ''.join(result)


def check_support(claims, sections):
    """M6: サポート要件チェック。請求項の語句が詳細説明に記載されているか確認。"""
    issues = []
    desc = sections.get("description", "")
    if not desc:
        issues.append({
            "milestone": "M6", "level": "warning",
            "msg": "発明の詳細な説明が見つかりません"
        })
        return issues, []

    # セクション別テキスト
    solve_text = _extract_section_text(desc,
        '課題を解決するための手段', '発明が解決しようとする課題')
    impl_text  = _extract_section_text(desc,
        '発明を実施するための形態', '発明を実施するための最良の形態',
        '実施例', '実施の形態', '実施形態')

    # support_table: [{noun, claims:[num...], in_solve:bool, in_impl:bool}]
    support_table = []
    noun_to_claims = {}  # noun → [claim_num, ...]

    # 最初のループで noun_to_claims を構築（最適化）
    for num in sorted(claims.keys()):
        body = claims[num]
        nouns = extract_nouns_for_support(body)
        for n in nouns:
            if len(n) >= 2:
                noun_to_claims.setdefault(n, [])
                if num not in noun_to_claims[n]:
                    noun_to_claims[n].append(num)

    # キャッシュした noun_to_claims を使用して support_table を構築
    for noun in sorted(noun_to_claims.keys()):
        in_desc  = noun in desc
        in_solve = noun in solve_text if solve_text else None
        in_impl  = noun in impl_text  if impl_text  else None
        support_table.append({
            "noun":     noun,
            "claims":   noun_to_claims[noun],
            "in_desc":  in_desc,
            "in_solve": in_solve,
            "in_impl":  in_impl,
        })

    # issueは「発明を実施するための形態に見当たらない」ものを報告
    # impl_textが空の場合は詳細説明全体(desc)で代替
    _primary_text = impl_text if impl_text else desc
    for num in sorted(claims.keys()):
        body = claims[num]
        nouns = extract_nouns_for_support(body)
        missing = sorted([n for n in nouns
                          if len(n) >= 2 and n not in _primary_text])
        if missing:
            sec_label = ('「発明を実施するための形態」'
                         if impl_text else '「発明の詳細な説明」')
            issues.append({
                "milestone": "M6", "level": "warning",
                "claim": num,
                "msg": f"請求項{num}：{sec_label}に見当たらない語句があります",
                "detail": "未記載の可能性：" + "、".join(missing[:12]) +
                          ("…" if len(missing) > 12 else "")
            })
    return issues, support_table


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
        from .m7_ambiguity import check_ambiguity
        m7_issues = check_ambiguity(claims)
    except Exception:
        m7_issues = []

    # M8: 記録項目チェック（遅延インポートで依存を分離）
    try:
        from .m8_docfields import check_docfields
        m8_issues = check_docfields(text)
    except Exception:
        m8_issues = []

    all_issues = m2_issues + m3_issues + m4_issues + m5_issues + m6_issues + m7_issues + m8_issues

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


# ══════════════════════════════════════════════════════════
# M3 名詞句グループ構築（右リスト用）
# ══════════════════════════════════════════════════════════

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
        candidates = [noun]  # 完全一致のみ（語幹フォールバック廃止）
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
                        prev_noun = _noun_after_zenshou(claim_tokens, j)
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


# ══════════════════════════════════════════════════════════
# ブロック構造構築（ビューア用）
# ══════════════════════════════════════════════════════════

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
    result = html_mod.escape(text)

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
        # 前記・上記・当該 ＋ 名詞句 → 全体を1スパン（水色）
        for word in ['前記', '上記', '当該']:
            if text[i:i+len(word)] == word:
                noun, consumed = extract_noun_phrase_after(text, i + len(word))
                is_err = (claim_num, noun) in m3_error_nouns
                cls = 'hl-zenshou-err' if is_err else 'hl-zenshou'
                safe_noun = esc(noun) if noun else ''
                # 表示テキスト = word + 元テキストのconsumed分（修飾語含む）
                raw_after = text[i + len(word): i + len(word) + consumed]
                full = esc(word + raw_after) if noun else esc(word)
                out.append(f'<span class="{cls}" data-noun="{safe_noun}" data-claim="{claim_num}">{full}</span>')
                i += len(word) + consumed
                matched = True
                break
        if not matched:
            # 該（当該以外）＋ 名詞句 → 全体を1スパン（水色）
            if text[i:i+1] == '該' and (i == 0 or text[i-2:i] != '当該'):
                noun, consumed = extract_noun_phrase_after(text, i + 1)
                is_err = (claim_num, noun) in m3_error_nouns
                cls = 'hl-zenshou-err' if is_err else 'hl-zenshou'
                safe_noun = esc(noun) if noun else ''
                raw_after = text[i + 1: i + 1 + consumed]
                full = '該' + esc(raw_after) if noun else '該'
                out.append(f'<span class="{cls}" data-noun="{safe_noun}" data-claim="{claim_num}">{full}</span>')
                i += 1 + consumed
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
