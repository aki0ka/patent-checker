# -*- coding: utf-8 -*-
"""
トークナイザーモジュール — fugashi による形態素解析

名詞句抽出・照応詞認識・先行詞候補収集のコア実装。
"""
import os
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
    各トークンは dict: {surf, pos, pos1, pos2, base, start, end}
    start/end はテキスト中の文字位置（offset）。
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
            'start': idx,
            'end':   idx + len(surf),
        })
        pos = idx + len(surf)
    return result

def _is_noun_tok(t):
    """名詞・接頭辞・接尾辞(名詞的) → 名詞句の構成要素"""
    p, p1 = t['pos'], t['pos1']
    if p == '名詞':   return True
    if p == '接頭辞': return True
    if p == '接尾辞' and p1 == '名詞的': return True
    return False

def _is_no_tok(t):
    """助詞「の」"""
    return t['pos'] == '助詞' and t['surf'] == 'の'

# 限定詞：これらの直後に「の＋名詞句」が続くとき全体を名詞句として取り込む
# 例：複数の検知部、一方の端部、他の装置、それぞれの素子
# 範囲接尾語：名詞句の末尾境界として扱う（「閾値以上」→「閾値」で停止）
_RANGE_SUFFIXES = {'以上', '以下', '未満', '超', '以内', '以外', '以降', '以前'}

# 繰り返し・概括接尾辞：先行詞照合では核名詞から除去したい語
_ITER_SUFFIXES = {'ごと', '毎', '向け', '用', '別', '系', '類'}

# 位置接尾辞：名詞句の末尾として付くが先行詞照合では除去したい語
# 例: 「距離内」→照合は「距離」で行う
_LOC_SUFFIXES = {'内', '外', '上', '下', '中', '間', '側', '前', '後', '先'}

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
        return True
    return False

_LIMITERS = {
    # 量化・選択
    '複数', '一部', '他', '別', '各', '全て', 'すべて', 'それぞれ',
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
_ORDINAL_MODS = {'一方', '他方'}

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
    """「少なくとも N つの」「２つの」などの量化修飾シーケンスをスキップし、
    後続の名詞句開始インデックスを返す。スキップできなければ i をそのまま返す。

    認識するパターン:
      (A) 形容詞「少なく」＋助詞「とも」＋ 数詞 ＋ 接尾辞(名詞的) ＋「の」
      (B) 副詞「少なくとも」（1トークン）＋ 数詞? ＋ 接尾辞(名詞的)? ＋「の」
      (C) 数詞 ＋ 接尾辞(名詞的) ＋「の」  例：２つの、１個の
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
        return i  # どのパターンにも一致しなかった

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

    「の」継続ルール（拡張版）:
      (1) 直前が 数詞 または 接頭辞         → 序数修飾「第１の〜」
      (2) 直前が 限定詞(_LIMITERS)         → 「複数の〜」「一方の〜」
      (3) 上記以外の普通名詞の後の「の」     → 停止（例：検知部の信号）

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
    while i < n:
        t = tokens[i]
        # 照応詞で停止
        if t['surf'] in _ZENSHOU_WORDS:
            break
        # 形式名詞（うち・とき・こと等）は名詞句の核ではないので停止
        if _is_formal_noun_tok(t):
            break
        # 繰り返し接尾辞（ごと・毎・用等）は核名詞の後なので停止
        if t['pos'] == '接尾辞' and t['surf'] in _ITER_SUFFIXES:
            break
        # 位置接尾辞（内・外・上等）が接尾辞品詞のとき停止
        if t['pos'] == '接尾辞' and t['surf'] in _LOC_SUFFIXES:
            break
        # 範囲接尾語（以上・以下・未満・超等）は名詞句に含めず停止
        if t['surf'] in _RANGE_SUFFIXES:
            break
        if _is_noun_tok(t):
            span.append(t)
            i += 1
        elif _is_no_tok(t):
            if not span:
                break
            prev = span[-1]
            # (1) 序数修飾：直前が数詞または接頭辞
            if prev['pos1'] == '数詞' or prev['pos'] == '接頭辞':
                span.append(t)
                i += 1
            # (2) 限定詞：複数の・一方の・他の 等
            elif prev['surf'] in _LIMITERS:
                span.append(t)
                i += 1
            else:
                break
        elif t['pos'] == '記号' and t['surf'] in ('・', '／'):
            span.append(t)
            i += 1
        else:
            break

    # 末尾の「の」は除く
    while span and span[-1]['surf'] == 'の':
        span.pop()
    return span

def _span_to_str(span):
    return ''.join(t['surf'] for t in span)

def _collect_defined_nouns(tokens):
    """トークン列から定義済み名詞句を収集（先行詞候補集合）。"""
    nouns = set()
    i = 0
    n = len(tokens)
    # 形式名詞・副詞可能名詞・副詞・感動詞は単独では先行詞候補に登録しない
    # → _is_formal_noun_tok() の品詞ルールで判定（リスト不要）
    # 追加除外語: 意味的に先行詞候補にならない語
    _SKIP_EXTRA = {'特徴', '内容', '種類'}
    while i < n:
        t = tokens[i]
        # 照応詞の直後は定義語ではなく参照語なのでスキップ
        # 照応詞トークン自体を飛ばすだけでなく、直後の名詞句全体もスキップする
        if t['surf'] in _ZENSHOU_WORDS:
            # 直後の名詞句を読み飛ばす
            skip_span = _noun_span(tokens, i + 1)
            i += 1 + (len(skip_span) if skip_span else 0)
            continue
        if _is_noun_tok(t):
            span = _noun_span(tokens, i)
            s = _span_to_str(span)
            # 除外条件:
            #   1) 1トークンで形式名詞 → 品詞ルールで除外
            #   2) _SKIP_EXTRA（特徴・内容・種類）
            #   3) 2文字未満
            is_skip = (len(s) < 2
                       or s in _SKIP_EXTRA
                       or (len(span) == 1 and _is_formal_noun_tok(span[0])))
            if not is_skip:
                nouns.add(s)
                # 量化修飾+核名詞 → 核名詞を先行詞候補として追加登録
                # パターンA: LIMITER + 'の' + 核名詞  例:「複数の送信波」→「送信波」
                # パターンB: 接頭辞(各/毎等) + 核名詞  例:「各送信波」→「送信波」
                if span and len(span) >= 2:
                    for k in range(len(span) - 1):
                        tok_k   = span[k]
                        tok_k1  = span[k+1]
                        # パターンA: LIMITER + 'の'
                        if (tok_k['surf'] in _LIMITERS and tok_k1['surf'] == 'の'
                                and k + 2 < len(span)):
                            core = _span_to_str(span[k+2:])
                            if len(core) >= 2 and core not in _SKIP_EXTRA:
                                nouns.add(core)
                            break
                        # パターンB: 接頭辞 + 名詞句（各送信波、毎送信等）
                        if (tok_k['pos'] == '接頭辞' and _is_noun_tok(tok_k1)):
                            core = _span_to_str(span[k+1:])
                            if len(core) >= 2 and core not in _SKIP_EXTRA:
                                nouns.add(core)
                            break
                # パターンC: 末尾トークンが数詞（符号番号）の場合
                # 「収容部２０」→「収容部」もベース名詞として登録
                # （「該収容部内」の先行詞「収容部」が見つかるようにするため）
                if (len(span) >= 2 and span[-1]['pos1'] == '数詞'):
                    base = _span_to_str(span[:-1])
                    if len(base) >= 2 and base not in _SKIP_EXTRA:
                        nouns.add(base)
            i += len(span) if span else 1
        else:
            i += 1
    return nouns

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
        return '', fallback_end

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
                    return y_a, span_a[-1]['end']
            # 段階A失敗 → 残りの動詞・助動詞もスキップ（従来の動作）
            while k < n and tokens[k]['pos'] in ('動詞', '助動詞'):
                k += 1
            if k < n and _is_noun_tok(tokens[k]) and not _is_fugo_tok(tokens[k]):
                span_y = _noun_span(tokens, k)
                y = _span_to_str(span_y)
                if len(y) >= 2:
                    return y, span_y[-1]['end']

    # 通常パターン
    span = _noun_span(tokens, zenshou_idx + 1)
    noun = _span_to_str(span)
    end_pos = span[-1]['end'] if span else fallback_end
    return noun, end_pos

def _found_in_scope(noun, scope_tokens):
    """noun が scope_tokens の定義済み名詞句に完全一致するか判定。

    意図的に完全一致のみ。「前記閾値」の先行詞は「閾値」として定義されている必要がある。
    「所定の閾値」という先行詞があっても「前記閾値」はエラー
    → 書き手は「前記所定の閾値」と書くか、先に「閾値」を独立定義すべき。

    例外: UniDicが「部内」「側面」等を複合名詞として一体化するケース。
    「該収容部内」→ noun="収容部内" のとき、末尾の「内」(_LOC_SUFFIXES) を
    ストリップして「収容部」でも再検索する。
    """
    defined = _collect_defined_nouns(scope_tokens)
    if noun in defined:
        return True
    # 末尾が位置接尾辞文字で終わる複合語（部内・領域内等）のフォールバック
    # UniDicが位置語を名詞として一体化した場合、ベース名詞でも先行詞を探す
    if noun and noun[-1] in _LOC_SUFFIXES and len(noun) > 2:
        base = noun[:-1]
        if len(base) >= 2 and base in defined:
            return True
    return False
