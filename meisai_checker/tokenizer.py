# -*- coding: utf-8 -*-
"""
トークナイザーモジュール — fugashi による形態素解析

名詞句抽出・照応詞認識・先行詞候補収集のコア実装。
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
import fugashi
import unidic_lite

# ── 必須依存 ──────────────────────────────
_dicdir = unidic_lite.DICDIR
_dicrc  = os.path.join(_dicdir, 'dicrc')
# Windowsパスのバックスラッシュをスラッシュに統一してMeCabに渡す
_dicdir_fwd = _dicdir.replace('\\', '/')
_dicrc_fwd  = _dicrc.replace('\\', '/')
_tagger = fugashi.GenericTagger(f'-d {_dicdir_fwd} -r {_dicrc_fwd}')

# ══════════════════════════════════════════════════════════
# M3: 前記・当該チェック  ※fugashiトークンベース実装
# ══════════════════════════════════════════════════════════

# 照応詞セット
_ZENSHOU_WORDS = {'前記', '上記', '当該', '該'}
# 当該スコープ限定（同一請求項の前方のみ）
_TOUGAI_WORDS  = {'当該', '該'}

def _tokenize(text):
    """テキストをトークンリストに変換。
    各トークンは dict: {surf, pos, pos1, pos2, base, cform, start, end}
    start/end はテキスト中の文字位置（offset）。
    cform は活用形（例：連用形-一般・連体形-一般）。動詞が名詞を修飾する
    連体形（関係節の述語）か、複合名詞を作る連用形かを区別するために使う。
    """
    global _tagger
    result = []
    pos = 0
    for w in _tagger(text):
        surf = w.surface
        feat = str(w.feature).split(',')
        def g(i): return feat[i].strip(" '(\"") if len(feat) > i else ''
        # テキスト中の位置を手動追跡
        idx = text.find(surf, pos)
        if idx < 0:
            idx = pos
        result.append({
            'surf': surf,
            'pos':  g(0),
            'pos1': g(1),
            'pos2': g(2),
            'base': g(7),
            'cform': g(5),
            'start': idx,
            'end':   idx + len(surf),
        })
        pos = idx + len(surf)
    return result

def _is_noun_tok(t):
    """名詞・接頭辞・接尾辞(名詞的/形状詞的) → 名詞句の構成要素"""
    p, p1 = t['pos'], t['pos1']
    if p == '名詞':   return True
    if p == '接頭辞': return True
    # 名詞的接尾辞に加え、形状詞的接尾辞（「的」）も名詞句継続として扱う
    # 例: 「段階的移行プロセス」を分断しないため
    if p == '接尾辞' and p1 in ('名詞的', '形状詞的'): return True
    return False

def _is_no_tok(t):
    """助詞「の」"""
    return t['pos'] == '助詞' and t['surf'] == 'の'

def _is_verb_noun_bridge_start(tokens, i):
    """tokens[i] が名詞句の先頭に立ちうる動詞連用形かどうか判定。

    「噛み合いギヤ」「位置決め工程」のように、連用形名詞化した語が
    UniDicでは動詞（一般・連用形）としてタグ付けされ、直後に名詞が
    続く場合は複合名詞の一部とみなす。連体形（「当接する背面」等）は
    関係節の述語であり複合語ではないため対象外。
    """
    n = len(tokens)
    t = tokens[i]
    if (t['pos'] == '動詞' and t['pos1'] == '一般'
            and not t['cform'].startswith('連体形')
            and not _is_functional_verb_phrase(tokens, i)
            and i + 1 < n and _is_noun_tok(tokens[i + 1])):
        return True
    return _causative_bridge_len(tokens, i) > 0

# 複合助詞（「〜により」「〜に基づき」「〜を介し」等）を構成する機能動詞。
# 直前の格助詞とセットで一つの助詞相当句をなすため、直後の名詞と複合語を
# 作ることはない。「無線通信部により間欠受信を…」の「間欠受信」が
# 「より間欠受信」に飲み込まれるのを防ぐ。
_FUNC_VERB_BASES = {
    '因る', '由る', '基づく', '基く', '介する', '応ずる', '応じる',
    '関する', '対する', '伴う', '従う', '沿う', '即する', '則する',
    '際する', '亘る', '拠る', '限る', '向ける', '通ずる', '通じる',
    '当たる', '当る', '先立つ',
}


def _is_functional_verb_phrase(tokens, i):
    """tokens[i] が「格助詞＋機能動詞」型の複合助詞の一部かどうか。

    「〜に|より」「〜に|基づき」「〜を|介し」のように、直前が格助詞で
    かつ動詞が機能動詞である場合は複合助詞であり、複合名詞の先頭には
    ならない。直前の格助詞を条件に加えることで、「第1歯車と噛み合いギヤ」
    のような真の連用形名詞化語（「噛み合う」等）には影響しない。
    """
    if i == 0:
        return False
    prev = tokens[i - 1]
    return (prev['pos'] == '助詞' and prev['pos1'] == '格助詞'
            and tokens[i]['base'] in _FUNC_VERB_BASES)

def _causative_bridge_len(tokens, i):
    """tokens[i] から「動詞未然形＋助動詞せ（せる）」の使役ブリッジが
    始まり、直後に名詞が続く場合にその長さ（常に2）を返す。該当しなければ0。

    「噛み合わせ歯車」のように、連用形名詞化語がさらに周辺文脈次第で
    「噛み合わ（未然形）＋せ（助動詞・せる連用形）」に分割されることが
    あり（UniDicのViterbi解析が前後の語で揺れるため）、この2トークンを
    まとめて複合名詞の先頭として扱う必要がある。
    """
    n = len(tokens)
    if (i + 2 < n
            and tokens[i]['pos'] == '動詞' and tokens[i]['pos1'] == '一般'
            and tokens[i]['cform'].startswith('未然形')
            and tokens[i + 1]['pos'] == '助動詞' and tokens[i + 1]['base'] == 'せる'
            and tokens[i + 1]['cform'].startswith('連用形')
            and _is_noun_tok(tokens[i + 2])):
        return 2
    return 0

# 限定詞：これらの直後に「の＋名詞句」が続くとき全体を名詞句として取り込む
# 例：複数の検知部、一方の端部、他の装置、それぞれの素子
# 範囲接尾語：名詞句の末尾境界として扱う（「閾値以上」→「閾値」で停止）
_RANGE_SUFFIXES = {'以上', '以下', '未満', '超', '以内', '以外', '以降', '以前'}

# 繰り返し・概括接尾辞：先行詞照合では核名詞から除去したい語
_ITER_SUFFIXES = {'ごと', '毎', '向け', '用', '別', '系', '類'}

# 位置接尾辞：名詞句の末尾として付くが先行詞照合では除去したい語
# 例: 「距離内」→照合は「距離」で行う
_LOC_SUFFIXES = {'内', '外', '上', '下', '中', '間', '側', '前', '後', '先'}

# 付帯接尾辞：「Xつきの/付きのY」は「XにYが付帯する」という記述であり、
# X・Yはそれぞれ独立した先行詞候補（複合名詞ではない）。
# 例:「温度計つきの発酵槽」→「温度計」と「発酵槽」を別々に登録する必要がある。
# 常に核名詞の直後で境界とし、次が名詞でも複合語として連結しない。
_ATTACH_SUFFIXES = {'つき', '付き'}

# 名詞句境界・先行詞照合フォールバック専用の位置接尾辞集合。
# 「間」は「ノード間」のように単独で新しい談話参照子（区間・空間概念）を
# 形成しうるため、ここでは核名詞への修飾語とみなさず除外する。
# （_is_formal_noun_tok の形式名詞判定では「間」を含む _LOC_SUFFIXES を使い続ける。
#  「工程の間に」等の時間的用法を実質名詞として扱う目的は別物なので影響しない）
# 「先」は「連絡先・送り先・入力先」等、語彙化された実質名詞（destination）を
# 形成することがほとんどで、「土台側」のような位置修飾の裸複合とは性質が異なる。
# 剥ぎ取ると「連絡先」が「連絡」に誤短縮されるため、境界判定からは除外する。
_LOC_SUFFIXES_BOUNDARY = _LOC_SUFFIXES - {'間', '先'}

# 形式名詞・副詞的名詞：名詞句の「継続」を打ち切るデリミタ
# 「複数の前記パルス光のうちパルス光」→「うち」で停止
# 意味的形式名詞：品詞だけでは判定できないため明示リスト
# （副詞可能名詞・副詞・感動詞は _is_formal_noun_tok() の品詞ルールで対応）
_FORMAL_NOUNS = {
    'こと', 'もの', 'はず', 'わけ', 'もと', 'とも', 'つもり', 'ともに',
}

# 副詞可能だが実質名詞として機能する語（_is_formal_noun_tokで除外しない）
# 位置語・範囲語・意味的実質名詞
_ADVERB_REAL_NOUNS = {
    '結果', '効果', '程度', '様子', '点',
    '分',  # 「所定期間分」等の助数詞的実質名詞
    '他',  # 「他のX」→ フル表現を先行詞として登録するため実質名詞扱い
}

def _is_formal_noun_tok(t):
    """形式名詞トークン判定。
    品詞ルール:
      名詞/普通名詞/副詞可能  → ため・とき・うち・ばあい・あいだ・あと・さい 等
                               ただし _LOC_SUFFIXES / _RANGE_SUFFIXES / _ADVERB_REAL_NOUNS は除外
      副詞 / 形状詞           → よう 等
      感動詞                  → まえ・ほう 等（fugashiが感動詞と解析）
    意味ルール:
      _FORMAL_NOUNS リスト    → こと・もの・はず・わけ・もと・とも・つもり・ともに
    """
    if t['surf'] in _FORMAL_NOUNS:
        return True
    p, p2 = t['pos'], t.get('pos2', '*')
    if p == '名詞' and p2 == '副詞可能':
        # 位置語・範囲語・実質名詞は形式名詞として扱わない
        s = t['surf']
        if s in _LOC_SUFFIXES or s in _RANGE_SUFFIXES or s in _ADVERB_REAL_NOUNS:
            return False
        return True
    if p in ('副詞', '形状詞', '感動詞'):
        # カタカナ形状詞（アクティブ・パッシブ等）は技術的複合語修飾語として除外しない
        if p == '形状詞' and t['surf'] and all('゠' <= c <= 'ヿ' for c in t['surf']):
            return False
        return True
    return False

_LIMITERS = {
    # 量化・選択
    '複数', '一部', '他', '各', '全て', 'すべて', 'それぞれ', '一',
    '一方', '他方', '両方', '双方', '少数', '多数', '全部',
    # 規定・特定（「所定の閾値」「特定の波長」等）
    '所定', '特定', '一定', '所望', '相互', '予定',
    # 参照指示
    '上述', '下述', '前述', '後述', '既述', '上記', '下記',
    # 程度・限界
    '最大', '最小', '最適', '最良', '最短', '最長', '最高', '最低',
    '任意', '適切', '適当', '適正',
}



# ケースA: 量化修飾語（同一符号を複数個まとめて指す）
_QUANT_MODS = {
    '各', '複数', '全て', 'すべて', 'それぞれ', '多数', '少数',
    '全部', '一部', '双方', '両方',
}

# ケースB: 序列修飾語（異なる符号を区別して指す）
_ORDINAL_MODS = {'一方', '他方', '他'}

def _strip_quant_prefix(name_toks):
    """名詞トークン列の先頭から量化/序列修飾語を除去し核名詞列と種別を返す。
    戻り値: (核名詞トークン列, 'quant' | 'ordinal' | 'mod' | None)
      'quant'  : 各・複数等（同一符号を複数指す）→ 要素名を核名詞に正規化
      'ordinal': 第N・一方/他方等（別符号を区別する）→ フル名のまま登録
      'mod'    : その他の修飾語+の（システム推奨の等）→ 核名詞のみ登録
    """
    if not name_toks:
        return name_toks, None
    t0 = name_toks[0]
    # 接頭辞「各」単独: 各センサ
    if t0['pos'] == '接頭辞' and t0['surf'] in _QUANT_MODS:
        return name_toks[1:], 'quant'
    # QUANT_MODS + 'の': 複数のセンサ
    if (t0['surf'] in _QUANT_MODS and len(name_toks) >= 2
            and name_toks[1]['surf'] == 'の'):
        return name_toks[2:], 'quant'
    # ORDINAL_MODS + 'の': 一方のセンサ
    if (t0['surf'] in _ORDINAL_MODS and len(name_toks) >= 2
            and name_toks[1]['surf'] == 'の'):
        return name_toks[2:], 'ordinal'
    # 接頭辞「第」+ 数詞: 第１センサ
    if (t0['pos'] == '接頭辞' and t0['surf'] == '第'
            and len(name_toks) >= 2 and name_toks[1]['pos1'] == '数詞'):
        return name_toks[2:], 'ordinal'
    # 汎用修飾語+「の」: 「システム推奨の」「その他の」等
    # 名詞列が「の」で終わっている場合: 「の」の前の名詞列を修飾語とみなす
    # ただし「の」は助詞なので名詞列には含まれない → _is_noun_tok条件で既に除外済み
    # → 名詞列の直前が「名詞+'の'」パターンを持つかどうかはトークン位置で判定
    # ここでは名_toks自体には「の」が入らないため、呼び出し側で判断することにする
    return name_toks, None

def _skip_quantifier(tokens, i):
    """「少なくとも N つの」などの量化修飾シーケンスをスキップし、
    後続の名詞句開始インデックスを返す。スキップできなければ i をそのまま返す。

    認識するパターン:
      (A) 形容詞「少なく」＋助詞「とも」＋ 数詞 ＋ 接尾辞(名詞的) ＋「の」
      (B) 副詞「少なくとも」（1トークン）＋ 数詞? ＋ 接尾辞(名詞的)? ＋「の」

    ※ 「Nつの」「N個の」等の単独数量表現（パターンC）はここで除去せず
      _noun_span 内の「の」継続ルール(3)で名詞句の一部として取り込む。
      これにより「１つの方向」「２個のセンサ」が先行詞として一体登録される。
    """
    n = len(tokens)
    j = i

    # (A) 形容詞「少なく」＋助詞「とも」
    if (j < n and tokens[j]['pos'] == '形容詞' and '少な' in tokens[j]['surf']):
        j += 1
        if j < n and tokens[j]['surf'] == 'とも':
            j += 1

    # (B) 副詞「少なくとも」1トークン
    elif (j < n and tokens[j]['pos'] == '副詞' and 'とも' in tokens[j]['surf']):
        j += 1

    if j == i:
        return i  # A/Bどのパターンにも一致しなかった

    # 数詞（任意）
    if j < n and tokens[j]['pos1'] == '数詞':
        j += 1
    # 接尾辞・名詞的（つ・個・本・台等、任意）
    if j < n and tokens[j]['pos'] == '接尾辞' and tokens[j]['pos1'] == '名詞的':
        j += 1
    # 「の」（任意だが後続名詞句が続くことを期待）
    if j < n and _is_no_tok(tokens[j]):
        j += 1

    # j が進んでいれば後続から名詞句開始
    return j if j > i else i

def _noun_span(tokens, start_idx):
    """tokens[start_idx] から始まる名詞句トークン列を返す。

    「の」継続ルール（改善版）:
      (1) 序数修飾のみ：「第１の〜」「2番目の〜」パターン
          - パターン1a: 接頭辞「第」+ 「の」
          - パターン1b: 「番目」+ 「の」
          ※ 「０の空ファイル」等の数値属性修飾は序数修飾ではなく停止
      (2) 限定詞修飾：「複数の〜」「一方の〜」等（_LIMITERS に登録された語）
      (3) 上記以外の「の」：停止（例：検知部の信号）

    量化修飾「少なくともNつの」は先行詞の核となる名詞句の前に置かれる
    限定詞として扱い、スキップして後続名詞句のみを返す。
    """
    n = len(tokens)

    # 量化修飾スキップ（少なくともNつの〜）
    after_quant = _skip_quantifier(tokens, start_idx)
    if after_quant > start_idx:
        # スキップ後に名詞句があればそれだけを返す
        span = _noun_span(tokens, after_quant)
        return span  # 量化部分は含めない（先行詞の核だけを返す）

    span = []
    i = start_idx
    ordinal_started = False  # 「第」で始まる序数修飾フラグ
    while i < n:
        t = tokens[i]
        # 照応詞で停止
        if t['surf'] in _ZENSHOU_WORDS:
            break
        # 「第」を見つけたら序数修飾モード開始
        # 「第１円形状」「第２両ユニット」のように、「第」の後ろの全ての名詞を連結する
        if t['pos'] == '接頭辞' and t['surf'] == '第':
            span.append(t)
            ordinal_started = True
            i += 1
            continue
        # 非カタカナ形状詞 + 後続名詞 → 複合名詞修飾語として継続（「新規〜」型）
        # 例: 「新規解析結果」「固有名称」など、な を挟まない形状詞+名詞複合語
        if (t['pos'] == '形状詞'
                and not all('゠' <= c <= 'ヿ' for c in (t['surf'] or ''))
                and i + 1 < n and _is_noun_tok(tokens[i + 1])):
            span.append(t)
            i += 1
            continue
        # 形式名詞（うち・とき・こと等）は名詞句の核ではないので停止
        # ただし直前が接頭辞のときは副詞可能名詞でも継続（不具合・大規模・副波長 等）
        if _is_formal_noun_tok(t):
            if not (span and span[-1]['pos'] == '接頭辞'):
                break
        # 繰り返し接尾辞（ごと・毎・用等）は核名詞の後なので停止
        if t['pos'] == '接尾辞' and t['surf'] in _ITER_SUFFIXES:
            # 次トークンが名詞なら複合語継続（判定用データ・車両向けシステム等）
            if i + 1 < n and _is_noun_tok(tokens[i + 1]):
                span.append(t)
                i += 1
                continue
            break
        # 付帯接尾辞（つき・付き）は常に境界。核名詞に連結せず、
        # 後続が名詞でも複合語化しない（「温度計」と「発酵槽」を分離登録するため）
        if t['pos'] == '接尾辞' and t['surf'] in _ATTACH_SUFFIXES:
            if not span:
                return []
            break
        # 位置接尾辞（内・外・上等）が接尾辞品詞のとき停止
        # 「間」は「ノード間」等の複合名詞を形成しうるため境界扱いしない（別枠で常に継続）
        # それ以外は「容器内空間」のように次が名詞なら複合語として継続、
        # 「基板上に」のように次が名詞でなければ位置修飾語とみなし停止
        if t['pos'] == '接尾辞' and t['surf'] in _LOC_SUFFIXES_BOUNDARY:
            if i + 1 < n and _is_noun_tok(tokens[i + 1]):
                span.append(t)
                i += 1
                continue
            break
        # 範囲接尾語（以上・以下・未満・超等）は名詞句に含めず停止
        # ただし span がここまで裸の数量表現（「２」「３個」等）のみの場合は
        # 範囲接尾語ではなく量化子プレフィックスの一部（「２以上の」）なので、
        # 「以上」＋「の」を消費して後続の実質名詞へ継続する（「前記２」誤認識対策）。
        # 「閾値以上の温度」のように span に実質名詞が既に入っている場合は
        # 従来通り break し「閾値」だけを返す。
        if t['surf'] in _RANGE_SUFFIXES:
            _is_bare_quant_span = (
                span and len(span) <= 2 and span[0]['pos1'] == '数詞'
                and (len(span) == 1
                     or (span[1]['pos'] == '接尾辞' and span[1]['pos1'] == '名詞的'))
            )
            if (_is_bare_quant_span and i + 1 < n and _is_no_tok(tokens[i + 1])
                    and i + 2 < n and _is_noun_tok(tokens[i + 2])):
                span.append(t)      # 以上/以下/未満/超 等
                span.append(tokens[i + 1])  # の
                i += 2
                continue
            break
        # 序数修飾中（「第」の後ろ）なら、数詞・名詞を全て連結
        if ordinal_started and (t['pos1'] == '数詞' or _is_noun_tok(t)):
            span.append(t)
            i += 1
            continue
        if _is_noun_tok(t):
            span.append(t)
            i += 1
            ordinal_started = False  # 最初の名詞で序数修飾モード終了
        elif (t['pos'] == '形状詞' and t['surf']
              and all('゠' <= c <= 'ヿ' for c in t['surf'])):
            # カタカナ形状詞（アクティブ・パッシブ等）は複合語修飾語として継続
            span.append(t)
            i += 1
        elif _is_no_tok(t):
            if not span:
                break
            prev = span[-1]
            # (1) 序数修飾：以下のパターンのみ
            #   パターン1a: 「第N」（接頭辞「第」+ 数詞）+ 「の」→ 「第1の〜」
            #   パターン1b: 「N番目」（数詞 + 「番目」）+ 「の」→ 「1番目の〜」
            is_ordinal = False
            # パターン1a: 直前が接頭辞「第」
            if prev['pos'] == '接頭辞' and prev['surf'] == '第':
                is_ordinal = True
            # パターン1a': 「第」+ 数詞 で span が終わっている（「第１の閾値」型）
            # MeCab は「第１」を接頭辞「第」＋数詞「１」に分割するため、
            # 「の」の直前トークンは数詞になる。この場合も序数修飾として継続し、
            # 「第１」で打ち切って「前記第１」を照応詞にしてしまうのを防ぐ。
            elif (prev['pos1'] == '数詞' and len(span) >= 2
                  and span[-2]['pos'] == '接頭辞' and span[-2]['surf'] == '第'):
                is_ordinal = True
            # パターン1b: 直前が「番目」
            elif prev['surf'] == '番目':
                is_ordinal = True

            if is_ordinal:
                span.append(t)
                ordinal_started = False  # 「の」で序数修飾モード終了
                i += 1
            # (2) 限定詞：複数の・一方の・他の 等
            # 「第一の」のように「一」が序数修飾中（ordinal_started）に登場した
            # 場合は数詞であって限定詞ではないため、この分岐の対象外にする
            # （「第１の」「第二の」と挙動を揃え、「一」だけが特別扱いされる
            # ことを避ける）。
            elif prev['surf'] in _LIMITERS and not ordinal_started:
                span.append(t)
                i += 1
            # (3) 助数詞接尾辞（つ・個・本等）先行の「の」→ 数量修飾として継続
            # 例: 「１つの方向」「２個のセンサ」「三本のコイル」
            # 先行詞を「方向」ではなく「１つの方向」として一体登録するため
            # 「対」は名詞タグだが数詞直後では助数詞的に機能するため同様に扱う
            # （「一対の脚回り部」→「一対」で打ち切らず「脚回り部」まで継続する）
            elif (((prev['pos'] == '接尾辞' and prev['pos1'] == '名詞的')
                   or prev['surf'] == '対')
                  and len(span) >= 2 and span[-2]['pos1'] == '数詞'):
                span.append(t)
                i += 1
            else:
                ordinal_started = False  # 「の」以外で序数修飾モード終了
                break
        elif t['pos'] == '記号' and t['surf'] in ('・', '／'):
            span.append(t)
            i += 1
        elif _causative_bridge_len(tokens, i):
            # 使役ブリッジ（噛み合わせ＝噛み合わ＋せ）：2トークンまとめて継続
            span.append(t)
            span.append(tokens[i + 1])
            i += 2
        elif (t['pos'] == '動詞' and t['pos1'] == '一般'
              and i + 1 < n and _is_noun_tok(tokens[i + 1])
              and not t['cform'].startswith('連体形')):
            # 動詞連用形が名詞列に挟まれた複合語（位置決め工程・孔あけ工程等）
            # 連体形（「当接する背面」の「接する」等）は関係節の述語であり
            # 複合語ではないため対象外（MeCabが「当接する」を「当」+「接する」
            # のように未知複合動詞を既知の断片へ分割した際、この動詞ブリッジが
            # 誤って断片と後続名詞まで一体で先行詞に取り込んでしまうのを防ぐ）
            # span が空（=このトークンが名詞句の先頭）でも許容する：
            # 「噛み合いギヤ」のように連用形名詞化した語がUniDicで動詞タグに
            # なる場合、複合語の先頭に立つことがあるため（実機バグ報告：
            # 「前記噛み合いギヤ」の先行詞がスコープ内に見つからないと誤検知）。
            span.append(t)
            i += 1
        else:
            break

    # 動詞ブリッジが連体形のためブロックされて止まった場合、直前の1トークン
    # だけの span（「当」「嵌」等）はその動詞（当接する・嵌着する等）が
    # MeCab未収録の複合動詞であるために生じた断片であり、独立した語として
    # 実在しない。裸の名詞が助詞なしで連体形動詞に直接隣接する構造は日本語
    # 文法上「その名詞＋動詞で1語の複合動詞」以外の解釈がないため、
    # 単独トークンの場合に限り安全に除外できる（2トークン以上の複合語が
    # たまたま連体形動詞と隣接するケースまでは誤爆を避けるため対象外）。
    if (span and len(span) == 1 and i < n
            and tokens[i]['pos'] == '動詞' and tokens[i]['pos1'] == '一般'
            and tokens[i]['cform'].startswith('連体形')
            and i + 1 < n and _is_noun_tok(tokens[i + 1])):
        return []

    # サ変語幹＋「する」で止まった場合の扱い:
    #   直後（するの次）が実質名詞なら、その語幹は独立した先行詞ではなく
    #   直後の動詞の一部（例：「回転する部材」の「回転」）なので登録しない。
    #   直後が形式名詞（こと・ため等）・文末・句読点なら、するは
    #   「〜することにより」のように事象を名詞化して継続させる用法であり、
    #   語幹（比較等）は事象名詞として先行詞になりうるため登録する
    #   （動詞由来先行詞として _collect_defined_nouns 側でマーキングする）。
    if span and i < n and tokens[i]['pos'] == '動詞' and tokens[i]['base'] == '為る':
        _after = tokens[i + 1] if i + 1 < n else None
        if not (_after is None or _is_formal_noun_tok(_after) or _after['pos'] == '補助記号'):
            return []

    # 末尾の「の」は除く
    while span and span[-1]['surf'] == 'の':
        span.pop()
    return span

def _span_to_str(span):
    return ''.join(t['surf'] for t in span)

def _find_dearu_defs(tokens):
    """「X である Y」定義構文を検出し、(genus_str, named_str, genus_start_idx) リストを返す。

    genus-differentia 定義パターン：
      X（属）= 型指定。独立した談話参照子ではなく、先行詞から除外する。
      Y（被定義名）= 命名先行詞として登録すべきもの。

    検出条件：
      noun_span(X) + で(助動詞) + ある(動詞, 非自立可能) + noun_span(Y・非形式名詞)

    自動除外（MeCab の品詞付与により）：
      「であるとき/こと」→ で が 接続詞 になるため不一致
      「であって」→ surf が 'ある' でないため不一致
    """
    defs = []
    n = len(tokens)
    i = 0
    while i < n:
        t = tokens[i]
        if t['surf'] in _ZENSHOU_WORDS:
            skip_span = _noun_span(tokens, i + 1)
            i += 1 + (len(skip_span) if skip_span else 0)
            continue
        _is_kata_keijo = (t['pos'] == '形状詞' and t['surf']
                          and all('゠' <= c <= 'ヿ' for c in t['surf']))
        _is_keijo_noun_prefix = (
            t['pos'] == '形状詞' and t['surf']
            and not all('゠' <= c <= 'ヿ' for c in t['surf'])
            and i + 1 < n and _is_noun_tok(tokens[i + 1])
        )
        if (_is_noun_tok(t) or _is_kata_keijo or _is_keijo_noun_prefix
                or _is_verb_noun_bridge_start(tokens, i)):
            span = _noun_span(tokens, i)
            if not span:
                i += 1
                continue
            j = i + len(span)
            # Look-ahead: で(助動詞) + ある(動詞, 非自立可能)
            if (j + 1 < n
                    and tokens[j]['surf'] == 'で'
                    and tokens[j]['pos'] == '助動詞'
                    and tokens[j + 1]['surf'] == 'ある'
                    and tokens[j + 1]['pos'] == '動詞'
                    and tokens[j + 1].get('pos1') == '非自立可能'):
                k = j + 2
                if (k < n
                        and _is_noun_tok(tokens[k])
                        and not _is_formal_noun_tok(tokens[k])):
                    named_span = _noun_span(tokens, k)
                    if named_span:
                        genus_str = _span_to_str(span)
                        named_str = _span_to_str(named_span)
                        # 「Xである請求項１に記載の...」は請求項参照であり定義構文ではない
                        if (len(genus_str) >= 2 and len(named_str) >= 2
                                and not named_str.startswith('請求項')):
                            defs.append((genus_str, named_str, i))
            i += len(span)
        else:
            i += 1
    return defs


def _get_title_noun_start(tokens):
    """請求項末尾の発明宣言名（タイトル名詞句）の開始トークンインデックスを返す。

    パターンA: [動詞] → [NP] → 。
    パターンB: [動詞] → 、 → [NP] → 。
    発見できない場合は None を返す。
    """
    if not tokens:
        return None
    n = len(tokens)

    # 末尾の句点をスキップ
    end = n - 1
    while end >= 0 and tokens[end]['surf'] in ('。', '　', ' '):
        end -= 1
    if end < 0:
        return None

    # 末尾から逆向きに名詞・「の」を収集して NP の先頭インデックスを求める
    pos = end
    while pos >= 0 and (_is_noun_tok(tokens[pos]) or _is_no_tok(tokens[pos])):
        pos -= 1
    noun_start = pos + 1

    if noun_start > end or noun_start == 0:
        return None

    # NP の先頭が「の」なら除去（助詞「の」で始まる NP は無効）
    while noun_start <= end and _is_no_tok(tokens[noun_start]):
        noun_start += 1
    if noun_start > end:
        return None

    # NP 直前のトークンがパターンA（動詞）またはパターンB（読点）なら発明宣言名と判定
    prev = tokens[noun_start - 1]
    if prev['surf'] == '、' or prev['pos'] == '動詞':
        return noun_start
    return None


@dataclass
class Occurrence:
    """先行詞候補の出現記録。

    position: トークン列内のインデックス（span 先頭）
    modifier: 直前の修飾節テキスト — Phase 2 で埋める
    is_new_dr: 産出動詞付きなら True（処理記述の裸名詞を除外用）— Phase 3 で埋める
    verb_origin: サ変語幹＋「する」（事象名詞化）由来の登録なら True
                 （例：「比較することにより」の「比較」）
    distributive: 「各N」「Nのそれぞれ」等、実際に分配（各要素ごとの束縛変数）が
                  確立された登場なら True。「複数のN」「全てのN」等は分配を伴わない
                  単なる群導入であり、それぞれ／各々等の分配マーカーが
                  伴わない限り False のまま（例：「複数のNを取得する」）。
    """
    position: int
    modifier: str | None = None
    is_new_dr: bool | None = None
    verb_origin: bool = False
    distributive: bool = False


# 「Nのそれぞれ」「Nの各々」等、Nに後続して分配を明示するマーカー
_DISTRIBUTIVE_SUFFIX_WORDS = {'それぞれ', '各々', 'おのおの'}

# 「Nごとに」「N毎に」等、Nに直接後続して分配を明示する接尾辞
# （「の」を挟まず名詞に直結する点が _DISTRIBUTIVE_SUFFIX_WORDS と異なる）
_ITER_DISTRIBUTIVE_SUFFIXES = {'ごと', '毎'}


def _collect_defined_nouns(tokens) -> dict[str, list['Occurrence']]:
    """トークン列から定義済み名詞句を収集（名詞句 → Occurrence リスト）。

    同一名詞句が複数回登場すれば list の長さがそれを示す。
    同一クレーム内での重複 DR 導入の検出に利用できる。
    """
    # 「X である Y」定義構文の属（X）は型指定であり談話参照子ではないため除外
    dearu_defs = _find_dearu_defs(tokens)
    dearu_genus_starts = {start for _, _, start in dearu_defs}

    nouns: dict[str, list[Occurrence]] = {}
    i = 0
    n = len(tokens)
    _SKIP_EXTRA = {'特徴', '内容', '種類'}
    while i < n:
        t = tokens[i]
        # 照応詞の直後は参照語なのでスキップ
        # 「前記複数のＸごとに」等の分配文脈は _collect_distributive_refs 側で
        # 別管理する（このループでは新規定義として登録しない：参照であって
        # 定義ではないため、ここで登録すると _bare_claims_tokenized 等の
        # 「定義済み名詞句」判定を汚染してしまう）。
        if t['surf'] in _ZENSHOU_WORDS:
            skip_span = _noun_span(tokens, i + 1)
            _consumed = 1 + (len(skip_span) if skip_span else 0)
            i += _consumed
            continue
        _is_kata_keijo = (t['pos'] == '形状詞' and t['surf']
                          and all('゠' <= c <= 'ヿ' for c in t['surf']))
        _is_keijo_noun_prefix = (
            t['pos'] == '形状詞' and t['surf']
            and not all('゠' <= c <= 'ヿ' for c in t['surf'])
            and i + 1 < n and _is_noun_tok(tokens[i + 1])
        )
        if (_is_noun_tok(t) or _is_kata_keijo or _is_keijo_noun_prefix
                or _is_verb_noun_bridge_start(tokens, i)):
            if i in dearu_genus_starts:
                span = _noun_span(tokens, i)
                i += len(span) if span else 1
                continue
            span = _noun_span(tokens, i)
            s = _span_to_str(span)
            _is_counter_expr = (
                span and len(span) <= 2
                and span[0]['pos1'] == '数詞'
                and (len(span) == 1
                     or (span[1]['pos'] == '接尾辞' and span[1]['pos1'] == '名詞的'))
            )
            is_skip = (not s
                       or s in _SKIP_EXTRA
                       or _is_counter_expr
                       or (len(span) == 1 and _is_formal_noun_tok(span[0])))
            if not is_skip:
                # サ変語幹＋「する」（事象名詞化）由来の登録かどうかを記録する。
                # 例：「比較することにより」の「比較」→ _noun_span が形式名詞
                # 続きを許容して登録したケース（_noun_span 参照）。
                _j = i + len(span)
                _verb_origin = (
                    _j < n and tokens[_j]['pos'] == '動詞'
                    and tokens[_j]['base'] == '為る'
                )
                # 分配マーカーの検出：
                #   前置型「各N」「それぞれのN」→ span 自体が分配を明示済み
                #   後置型「Nのそれぞれ」「Nの各々」→ span 直後の の＋それぞれ等
                _distributive = (
                    (span and span[0]['surf'] == '各')
                    or s.startswith('それぞれの')
                    or (_j + 1 < n and tokens[_j]['surf'] == 'の'
                        and tokens[_j + 1]['surf'] in _DISTRIBUTIVE_SUFFIX_WORDS)
                    or (_j + 1 < n and tokens[_j]['pos'] == '接尾辞'
                        and tokens[_j]['surf'] in _ITER_DISTRIBUTIVE_SUFFIXES
                        and tokens[_j + 1]['surf'] == 'に')
                )
                nouns.setdefault(s, []).append(
                    Occurrence(position=i, verb_origin=_verb_origin,
                               distributive=_distributive))
                # パターンC: 末尾トークンが数詞（符号番号）の場合
                # 「収容部２０」→「収容部」もベース名詞として登録
                if (len(span) >= 2 and span[-1]['pos1'] == '数詞'):
                    base = _span_to_str(span[:-1])
                    if len(base) >= 2 and base not in _SKIP_EXTRA:
                        nouns.setdefault(base, []).append(Occurrence(position=i))
            i += len(span) if span else 1
        else:
            i += 1
    return nouns


def _collect_distributive_refs(tokens) -> dict[str, list['Occurrence']]:
    """「前記複数のＸごとに」「当該Ｘの各々」等、参照側（前記/当該＋名詞句）に
    分配マーカーが続く出現だけを収集する（名詞句 → Occurrence リスト）。

    これは照応（reference）であって新規定義ではないため、_collect_defined_nouns
    の戻り値（定義済み名詞句）とは別管理にする。「当該Ｘ」の束縛変数回収
    （同一請求項内で分配文脈が確立しているかの判定）専用。
    _bare_claims_tokenized 等の定義済み名詞句判定にこの出現を含めると、
    参照に過ぎない「前記複数のＸごとに」を新規定義と誤認し、
    先行詞重複の誤警告を生む（実案件で確認：分配マーカー越しの当該参照）。
    """
    refs: dict[str, list[Occurrence]] = {}
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t['surf'] in _ZENSHOU_WORDS:
            skip_span = _noun_span(tokens, i + 1)
            _consumed = 1 + (len(skip_span) if skip_span else 0)
            if skip_span:
                _k = i + 1 + len(skip_span)
                _ref_distributive = (
                    (_k + 1 < n and tokens[_k]['surf'] == 'の'
                     and tokens[_k + 1]['surf'] in _DISTRIBUTIVE_SUFFIX_WORDS)
                    or (_k + 1 < n and tokens[_k]['pos'] == '接尾辞'
                        and tokens[_k]['surf'] in _ITER_DISTRIBUTIVE_SUFFIXES
                        and tokens[_k + 1]['surf'] == 'に')
                )
                if _ref_distributive:
                    _ref_key = _span_to_str(skip_span)
                    refs.setdefault(_ref_key, []).append(
                        Occurrence(position=i + 1, distributive=True))
            i += _consumed
            continue
        i += 1
    return refs

def _is_fugo_tok(t):
    """全角数字のみからなるトークン → 符号候補（pos1は数詞・普通名詞どちらでも可）"""
    return (t['pos'] == '名詞'
            and t['pos1'] in ('数詞', '普通名詞', '固有名詞')
            and len(t['surf']) >= 1
            and all('\uff10' <= c <= '\uff19' for c in t['surf']))

def _is_alpha_fugo_tok(t):
    """全角英字1〜2文字のトークン → 符号サフィックス候補"""
    import re
    return bool(re.fullmatch(r'[Ａ-Ｚａ-ｚ]{1,2}', t['surf']))

def _noun_after_zenshou(tokens, zenshou_idx):
    """照応詞トークンの直後から名詞句を取得して (noun_str, end_char_pos) を返す。

    end_char_pos: 抽出した名詞句の末尾文字位置（マーカー終端に使用）。
                  名詞が取れなかった場合は照応詞トークン自体の end を返す。

    通常ケース: 前記 → 名詞句をそのまま返す。

    「前記Xした/されたY」パターン（サ変可能名詞の連体節）:
      例: 「前記分析した関係」→ 「関係」
          「前記受信した〜データ」→ 「〜データ」
      条件: 前記直後がサ変可能名詞(X) + 動詞・助動詞列 + 名詞句(Y) の形。
            接尾辞（済み等）が続く場合はこのパターンに該当しない。

      段階A: た/だ の直後で一旦停止し _noun_span を試みる。
             成功すれば Y を返す（「前記判定した結果」→「結果」等）。
      段階A失敗: 残り動詞もすべてスキップして従来通り Y を返す。
    """
    j = zenshou_idx + 1
    n = len(tokens)
    fallback_end = tokens[zenshou_idx]['end'] if zenshou_idx < n else 0
    if j >= n:
        return '', fallback_end, fallback_end

    t1 = tokens[j]

    # 「前記Xした/されたY」パターン検出
    if t1['pos'] == '名詞' and t1.get('pos2') == 'サ変可能':
        k = j + 1
        if k < n and tokens[k]['pos'] == '接尾辞':
            pass  # 「学習済み〜」は通常パターンへ
        elif k < n and tokens[k]['pos'] in ('動詞', '助動詞'):
            # 段階A: た/だ の直後で一旦停止
            while k < n and tokens[k]['pos'] in ('動詞', '助動詞'):
                if tokens[k]['surf'] in ('た', 'だ'):
                    k += 1
                    break
                k += 1
            # 段階A: 停止点で noun_span を試みる
            if k < n:
                span_a = _noun_span(tokens, k)
                y_a = _span_to_str(span_a)
                if len(y_a) >= 2 and not (span_a and _is_fugo_tok(span_a[0])):
                    return y_a, span_a[0]['start'], span_a[-1]['end']
            # 段階A失敗 → 残りの動詞・助動詞もスキップ（従来の動作）
            while k < n and tokens[k]['pos'] in ('動詞', '助動詞'):
                k += 1
            if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
                span_y = _noun_span(tokens, k)
                y = _span_to_str(span_y)
                if len(y) >= 2:
                    # 直前トークンが一般動詞（連用形として機能）なら複合名詞として結合
                    # 例: 「判定した汚れ度合い」→「汚れ」(動詞/一般) + 「度合い」= 「汚れ度合い」
                    if (k > 0 and tokens[k-1]['pos'] == '動詞'
                            and tokens[k-1]['pos1'] == '一般'):
                        return tokens[k-1]['surf'] + y, tokens[k-1]['start'], span_y[-1]['end']
                    return y, span_y[0]['start'], span_y[-1]['end']

    # 数詞＋「の」パターン（「一のN」等の限定量化子）
    # 「前記一のひねり操作」→「一のひねり操作」（ひねりは連用形の複合名詞
    # 形成なので操作と一体、_noun_span の動詞ブリッジ規則で吸収される）
    # 「第N」（接頭辞「第」付き）は序数修飾として通常パターンに任せる
    if (t1['pos1'] == '数詞'
            and j + 1 < n and tokens[j + 1]['surf'] == 'の'):
        k = j + 2
        # 動詞を読み飛ばす。ただし連用形（「ひねり操作」の「ひねり」等、
        # 複合名詞を形成する形）は記述的修飾ではないため verb_modified の
        # 根拠にしない。連体形（「ひねる操作」等、関係節として後続名詞を
        # 修飾する形）のみを真の記述的修飾として扱う。
        _verb_skipped = False
        while k < n and tokens[k]['pos'] == '動詞':
            if tokens[k]['cform'].startswith('連体形'):
                _verb_skipped = True
            k += 1
        if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
            span_y = _noun_span(tokens, k)
            y = _span_to_str(span_y)
            if len(y) >= 2:
                if _verb_skipped:
                    return y, span_y[0]['start'], span_y[-1]['end']
                # 「一の」のように動詞を伴わない裸の量化子は記述的修飾では
                # ないため、noun_start を「一」の開始位置（zenshou直後）に
                # して verb_modified（記述照応詞）判定を誤発火させない。
                # 「一の」は局所的に新しい名前「一のN」を生成し、脱落させると
                # 先行詞不一致になる（project_toukei_checker_design参照）。
                # 定義側（_collect_defined_nouns）は _LIMITERS 経由の _noun_span
                # で「一の」＋連用形複合（例：一のひねり操作）まで一体で登録する
                # ため、参照側も文字列結合ではなく同じ _noun_span を「一」の
                # トークン位置から呼び直し、両者のキーを一致させる。
                if t1['surf'] == '一':
                    full_span = _noun_span(tokens, j)
                    if full_span:
                        return (_span_to_str(full_span), full_span[0]['start'],
                                full_span[-1]['end'])
                return y, tokens[j]['start'], span_y[-1]['end']

    # 形状詞修飾パターン
    # 弁別基準: 助動詞「な（だ連体形）」の有無
    #   形状詞 + な(助動詞-ダ/連体形) + 名詞 → 記述照応詞（「新たな〜」型）
    #   形状詞 + 名詞（直接）          → 複合名詞ラベル候補（「新規〜」型）→ 通常パターンへ
    if t1['pos'] == '形状詞':
        k = j + 1
        if (k < n
                and tokens[k]['pos'] == '助動詞'
                and tokens[k]['surf'] == 'な'):
            k += 1  # な をスキップ
            if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
                span_y = _noun_span(tokens, k)
                y = _span_to_str(span_y)
                if len(y) >= 2:
                    return y, span_y[0]['start'], span_y[-1]['end']
        # な なし（複合名詞）→ fall through して通常パターンへ

    # 形容詞修飾パターン（〜い + 名詞 → 常に記述照応詞）
    # 形容詞は複合名詞を形成しないため、な の有無にかかわらずスキップ
    elif t1['pos'] == '形容詞':
        k = j + 1
        if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
            span_y = _noun_span(tokens, k)
            y = _span_to_str(span_y)
            if len(y) >= 2:
                return y, span_y[0]['start'], span_y[-1]['end']

    # 副詞修飾パターン（「あらかじめ定められた閾値」「事前に設定された値」型）
    elif t1['pos'] == '副詞':
        k = j + 1
        while k < n and tokens[k]['pos'] in ('動詞', '助動詞'):
            k += 1
        if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
            span_y = _noun_span(tokens, k)
            y = _span_to_str(span_y)
            if len(y) >= 2:
                return y, span_y[0]['start'], span_y[-1]['end']

    # 通常パターン
    span = _noun_span(tokens, zenshou_idx + 1)
    noun = _span_to_str(span)
    if span:
        return noun, span[0]['start'], span[-1]['end']
    return noun, fallback_end, fallback_end

# 「群」として導入する量化子（早いものがち戦略で「複数のN」相当として扱う）
# 「複数の」のみ対象。「各N」「それぞれのN」等は分配であり、ここでは扱わない。
_PLURAL_INTRO_MODS = {'複数'}


def _scan_first_seen_as_plural(tokens):
    """トークン列を文字列順に走査し、各核名詞 N の「初出時の量化子状態」を記録する。

    「早いものがち戦略」:
      - 「複数のN」として先に登場した核名詞 N → True
      - 裸名詞 N として先に登場した核名詞 N → False
    一度記録した N は上書きしない（初出のみ）。

    照応詞（前記・上記・当該・該）の直後の名詞句は参照であって導入ではないため
    スキップする（_collect_defined_nouns と同じ扱い）。

    戻り値: dict[核名詞 str, bool]
    """
    result = {}
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        # 照応詞の直後の名詞句は参照なのでまとめてスキップ
        if t['surf'] in _ZENSHOU_WORDS:
            skip_span = _noun_span(tokens, i + 1)
            i += 1 + (len(skip_span) if skip_span else 0)
            continue
        # 「複数 の N」パターン: 群としての導入
        if (t['surf'] in _PLURAL_INTRO_MODS
                and i + 2 < n and tokens[i + 1]['surf'] == 'の'
                and _is_noun_tok(tokens[i + 2])):
            span = _noun_span(tokens, i + 2)
            core = _span_to_str(span)
            if len(core) >= 2 and core not in result:
                result[core] = True
            # 「複数の」+核名詞をまとめて消費
            i = i + 2 + (len(span) if span else 1)
            continue
        # 通常の名詞句（裸名詞としての登場）
        if _is_noun_tok(t) or _is_verb_noun_bridge_start(tokens, i):
            span = _noun_span(tokens, i)
            s = _span_to_str(span)
            if len(s) >= 2 and s not in result:
                result[s] = False
            i += len(span) if span else 1
            continue
        i += 1
    return result


_LEADING_QUANT_PREFIXES = [
    ('各', 1),
    ('複数の', 3),
    ('それぞれの', 5),
    ('全ての', 4),
    ('すべての', 5),
    ('全部の', 4),
]

def _strip_leading_quantifier(noun):
    """「各X」「複数のX」等の先頭量化子を除去して核名詞を返す。除去できなければそのまま返す。"""
    for prefix, n in _LEADING_QUANT_PREFIXES:
        if noun.startswith(prefix) and len(noun) > n:
            return noun[n:]
    return noun

# スペルアウト括弧書きパターン（「ＧＮＳＳ（Global Navigation Satellite System）受信機」等）
_PAREN_PAT = re.compile(r'（[^）]+）')


def _spell_out_bridge(noun, scope_tokens):
    """noun がスペルアウト括弧書きを含む形でスコープ内に定義されているか調べる。

    MeCab は「ＧＮＳＳ（Global…）受信機」を ＧＮ|ＳＳ|（|Global|…|）|受信|機 と分割し、
    _collect_defined_nouns は括弧内容を別名詞として登録する。
    そのため、括弧付き noun は defined には入らない。

    代わりにトークン surf 列を連結したスコープ文字列を使い、
    noun の各文字の間に括弧書きが任意挿入されたパターンで regex 検索する。
    マッチした場合、表示用に「noun の前半部（…）後半部」形式の文字列を返す。
    """
    # スコープ内で括弧付きトークンが存在しなければ即 None
    if not any(t['surf'] == '（' for t in scope_tokens):
        return None
    scope_text = ''.join(t['surf'] for t in scope_tokens)
    # noun を re.escape した各文字の間に (?:（[^）]+）)? を挟んだパターンを構築
    # 例: "ＧＮＳＳ受信機" → Ｇ(?:（[^）]+）)?Ｎ(?:（...）)?Ｓ...機
    chars = list(noun)
    pattern = r'(?:（[^）]+）)?'.join(re.escape(c) for c in chars)
    m = re.search(pattern, scope_text)
    if m and m.group(0) != noun:
        return m.group(0)  # 括弧書きを含む形（スコープ文字列から取得）
    return None


def _found_in_scope_ex(noun, scope_tokens, plural_map=None, allow_modifier_bridge=True):
    """noun が scope_tokens 内の先行詞候補に一致するか判定。

    戻り値: (found: bool, bridge_original: str | None, verb_origin_only: bool,
             head_only_source: str | None)
    bridge_original が非Noneの場合、スペルアウト括弧書き省略によるブリッジマッチを示す。
    verb_origin_only は、noun のスコープ内の登場が全てサ変語幹＋「する」由来
    （例：「比較することにより」の「比較」）である場合に True。
    head_only_source は、例外3（_LIMITERS限定詞＋核名詞のブリッジ）が一致した際の
    先行詞側の完全な文字列（例：「所定の分岐画像」）。allow_modifier_bridge=False の
    場合、この一致は found=True に反映せず（＝主要部のみ一致は解決とみなさない）、
    呼び出し元が「当該」の③（修飾語脱落）ERROR判定に使えるようこの値だけ返す。

    allow_modifier_bridge: False にすると例外3（限定詞剥ぎ取りブリッジ）の一致を
    found としては採用しない。「前記」は従来通り True（許容）のまま使う。
    「当該」は False を渡し、修飾語省略を曖昧性確定として扱う。

    plural_map: 例外4の「一のN」判定で使う「核名詞→複数形が先行しているか」の
    事前計算済みマップ（呼び出し元が請求項をまたいだ範囲で計算したもの）。
    None の場合は scope_tokens だけから計算する（従来通り、同一スコープ限定）。
    前記・上記は祖先請求項を含めた範囲のマップを渡すことで、「複数のX」が
    親請求項にしかない場合でも「一のX」の保持要求を正しく判定できる。
    当該・該は意図的に同一請求項スコープに閉じるため plural_map を渡さない。

    例外1: UniDicが「部内」等を複合名詞化するケース → 末尾位置接尾辞を除去して再検索。
    例外2: スペルアウトブリッジ（「ＧＮＳＳ受信機」←「ＧＮＳＳ（…）受信機」）。
    例外3: 限定詞+の+核名詞（「所定の分岐画像」）の場合、限定詞を除外した核名詞でも再検索。

    注：量化子の剥ぎ取りは行わない。「前記各N」は「各N」として前方検索する。
    「複数のN」と導入されたなら「前記複数のN」で照応するのが正しい形。

    【設計メモ：位置接尾辞処理の非対称性】
    例外1は「照応詞側の末尾 _LOC_SUFFIXES を剥いて先行詞を探す」片方向処理。
    逆方向（先行詞が「一表面側」で照応詞が「前記一表面」）は意図的に処理しない。
    理由：先行詞に「側」しかなければ「表面」という談話参照子は未導入であり、
    「前記一表面」はその意味では誤りと判断すべきため。
    逆方向まで許容すると「入力側」を導入しただけで「前記入力」が通ってしまう。
    特許5421742（パナソニック トランス）の「前記一表面」errorはこの仕様による正検出。
    """
    defined = _collect_defined_nouns(scope_tokens)
    if noun in defined:
        occs = defined[noun]
        return True, None, bool(occs) and all(o.verb_origin for o in occs), None
    if noun and noun[-1] in _LOC_SUFFIXES_BOUNDARY and len(noun) > 2:
        # 末尾の位置接尾辞を除去して再検索（例：「蓋部内」→「蓋部」）
        # MeCabが「部内」を複合名詞化するケース（蓋部内/収容部内等）でも対応するため
        # 再トークナイズ検証は行わず、base が定義済みかどうかだけで判定する
        base = noun[:-1]
        if len(base) >= 2 and base in defined:
            occs = defined[base]
            return True, None, bool(occs) and all(o.verb_origin for o in occs), None
    # 例外3: 限定詞+核名詞で再検索（「分岐画像」→「所定の分岐画像」）
    # 「所定の分岐画像」で定義されている場合、「前記分岐画像」で照応できるようにする
    # ただし同一性変更限定詞（他・別）は除外：「他のX」≠「X」なので「前記X」では照応不可
    # 量化子系限定詞（各・複数・それぞれ等）も除外：カーディナリティを持つため
    # 「複数のN」と導入されたなら「前記複数のN」で照応するのが正しい形であり、
    # 剥ぎ取って裸のNで照応させると束縛変数のカーディナリティ整合性チェックを
    # 迂回してしまう（上記docstring「量化子の剥ぎ取りは行わない」の趣旨通り）。
    head_only_source = None
    for limiter in sorted(_LIMITERS, key=len, reverse=True):
        # 「一」は他の量化子系限定詞と同じくこのループでは常にスキップし、
        # 判定は例外4（スコープベースの群ドメイン判定）に一本化する。
        if limiter in _ORDINAL_MODS or limiter in _QUANT_MODS or limiter == '一':
            continue
        with_limiter = limiter + 'の' + noun
        if with_limiter in defined:
            if allow_modifier_bridge:
                return True, None, False, None
            # 当該・該：主要部のみ一致（修飾語脱落）は found とせず、
            # 呼び出し元が③ERRORを組み立てられるよう先行詞側の文字列だけ残す。
            head_only_source = with_limiter
            break
    # 例外4: 数量修飾「Nつの」「N個の」等+核名詞で導入された場合の核名詞単独照応
    # 「１つのセンサ」で導入 → 「前記センサ」で照応するパターンを許容
    # （「少なくとも」を伴う場合は既存の先行詞が核名詞で登録されるため対象外）
    _plural_map = plural_map
    for dn in defined:
        if not dn.endswith('の' + noun):
            continue
        prefix = dn[:-(len(noun) + 1)]  # 「の」+ noun を除いた前置部（「１つ」等）
        if not prefix:
            continue
        prefix_toks = _tokenize(prefix)
        # 「一」単独はスコープベースで判定する：「複数のnoun」等、同じ核名詞の
        # 群（複数形）先行詞が同一スコープに存在する場合のみ、「一のnoun」への
        # 保持を要求する（「複数のXのうち一のX」で群と個体を区別する必要が
        # あるため）。群先行詞が存在しなければ「一の」は不定の存在導入
        # （「一の願書」のように法令文体で談話冒頭に立つ用例が実在する）と
        # みなし、「１つの」「２個の」等と同様に橋渡しを許容する。
        # 「少なくとも一の」は群の有無に関わらず不定の存在導入（分割選択では
        # ない）なので常に橋渡しを許容する。
        if prefix == '一':
            _occs = defined.get(dn, [])
            _sukunakutomo = any(
                (o.position >= 1 and scope_tokens[o.position - 1]['surf'] == 'とも')
                or (o.position >= 1 and '少なくとも' in scope_tokens[o.position - 1]['surf'])
                for o in _occs
            )
            if _plural_map is None:
                _plural_map = _scan_first_seen_as_plural(scope_tokens)
            _has_plural_domain = _plural_map.get(noun, False)
            if not _sukunakutomo and _has_plural_domain:
                continue
        if ((len(prefix_toks) == 1 and prefix_toks[0]['pos1'] == '数詞')
                or (len(prefix_toks) == 2
                    and prefix_toks[0]['pos1'] == '数詞'
                    and prefix_toks[1]['pos'] == '接尾辞'
                    and prefix_toks[1]['pos1'] == '名詞的')):
            return True, None, False, None
    # スペルアウトブリッジフォールバック
    bridge = _spell_out_bridge(noun, scope_tokens)
    if bridge:
        return True, bridge, False, None
    return False, None, False, head_only_source


def _found_in_scope(noun, scope_tokens):
    """noun が scope_tokens の定義済み名詞句に完全一致するか判定。

    意図的に完全一致のみ。「前記閾値」の先行詞は「閾値」として定義されている必要がある。
    「所定の閾値」という先行詞があっても「前記閾値」はエラー
    → 書き手は「前記所定の閾値」と書くか、先に「閾値」を独立定義すべき。

    例外1: UniDicが「部内」「側面」等を複合名詞として一体化するケース。
    「該収容部内」→ noun="収容部内" のとき、末尾の「内」(_LOC_SUFFIXES) を
    ストリップして「収容部」でも再検索する。

    例外2: 量化子付き照応詞（「各X」「複数のX」等）。
    「前記各送電コイル」→ noun="各送電コイル" のとき、先行詞DBには"送電コイル"のみ
    登録されているケースがある。量化子を除去した核名詞でも再検索する。

    例外3: スペルアウトブリッジ（_found_in_scope_ex 参照）。
    ブリッジ情報が不要な呼び出し元向けのシム。
    """
    found, _, _, _ = _found_in_scope_ex(noun, scope_tokens)
    return found
