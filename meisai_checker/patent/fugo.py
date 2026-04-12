# -*- coding: utf-8 -*-
"""M4: 符号チェック（特許法第37条・36条6項関連）。

図面符号（全角数字/英字略称+数字）と変数記号（全角英字1文字+添字）の
要素名との対応整合性をチェックする。

依存: tokenizer.py（MeCab/fugashi 必須）
"""

from __future__ import annotations

import re
from collections import Counter

from ..parser import z2h
from ..tokenizer import (
    _tokenize,
    _is_noun_tok,
    _is_formal_noun_tok,
    _strip_quant_prefix,
    _is_fugo_tok,
    _is_alpha_fugo_tok,
    _ZENSHOU_WORDS,
    _ORDINAL_MODS,
)


# ── 文字種ヘルパー ──────────────────────────────────────────

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


# ── 公報番号パターン ──────────────────────────────────────────

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
                    # 全角英字1文字 + 直後が全角数字 → 変数記号（Ｖ１等）で停止
                    # 「電圧Ｖ１」の「Ｖ」で止めて「電圧Ｖ」を要素名にしない
                    surf_j = tokens[j]['surf']
                    if (len(surf_j) == 1
                            and _is_zenkaku_alpha(surf_j[0])
                            and j + 1 < n and _is_fugo_tok(tokens[j + 1])):
                        break
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
        fugo_to_names.setdefault(fugo, {})[name] = \
            min(fugo_to_names.get(fugo, {}).get(name, off), off)
        name_to_fugos.setdefault(name, {})[fugo] = \
            min(name_to_fugos.get(name, {}).get(fugo, off), off)
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
        vsym_to_phys.setdefault(vsym, {})[phys] = \
            min(vsym_to_phys.get(vsym, {}).get(phys, off), off)
        phys_to_vsym.setdefault(phys, {})[vsym] = \
            min(phys_to_vsym.get(phys, {}).get(vsym, off), off)

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
