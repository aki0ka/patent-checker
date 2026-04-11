"""M7: 請求項の係り受け曖昧性チェック

fugashi の品詞情報 + 正規表現により、特許請求項で頻出する
係り受け曖昧パターンを検出して警告を発する。

対象パターン:
  P1: 連用形の連続 (〜し、〜し、〜する)
      → 各節がどこにかかるか不明瞭になりやすい
  P2: AまたはBのC / AもしくはBのC
      → (A or B) の C か、A or (B の C) か
  P3: 長い連体修飾節の連鎖 (〜する〜する〜する名詞)
      → どの動詞がどの名詞を修飾するか不明瞭
  P4: 「〜を〜を」の二重目的語
      → 並列か入れ子か不明瞭
  P5: 読点のない長文請求項
      → 係り先が特定しにくい
"""

import re
from typing import Any
from ..tokenizer import _tokenize

# ──────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────

# 連用形として扱う活用形ラベル（unidic）
_RENYOU_FORMS = {
    '連用形-一般', '連用形-ニ', '連用形-促音便', '連用形-撥音便',
    '連用形-融合', '連用形-省略',
}

# 接続助詞（文節境界）
_SETSUZOKU_JOSHI = {'て', 'で', 'に', 'ながら', 'つつ', 'ば', 'たり', 'だり'}

# 並列接続詞
_PARALLEL_CONJ = {'または', 'もしくは', 'あるいは', 'ならびに', 'および'}

# 長文判定の閾値（文字数）
_LONG_CLAUSE_CHARS = 60   # 読点なしでこれ以上続いたら警告
_LONG_MODIFIER_VERBS = 3  # 連体修飾の動詞がこれ以上連続したら警告


# ──────────────────────────────────────────────
# P1: 連用形の連続
# ──────────────────────────────────────────────

def _check_renyou_chain(claim_num: int, body: str) -> list[dict]:
    """連用形の連続（〜し、〜し、〜する）を検出する。

    連用形トークンが読点を挟まず3つ以上連続した場合に警告。
    接続助詞「て/で」単独は除外（明確な従属節を形成するため）。
    """
    issues = []
    tokens = _tokenize(body)
    chain = []

    for i, t in enumerate(tokens):
        form = t.get('cform', '')
        pos = t['pos']

        # 連用形の動詞・形容詞・助動詞
        if pos in ('動詞', '形容詞', '助動詞') and form in _RENYOU_FORMS:
            # 直後が「て/で」のみの接続助詞なら明確な従属節 → スキップ
            next_surf = tokens[i+1]['surf'] if i+1 < len(tokens) else ''
            if next_surf in ('て', 'で'):
                chain = []
                continue
            chain.append((i, t['surf']))

        elif t['surf'] == '、':
            # 読点は連鎖を継続させる区切り
            pass

        elif pos in ('名詞', '助詞', '記号') and t['surf'] not in ('、', '。'):
            # 連鎖終端
            if len(chain) >= 3:
                surfs = '、'.join(s for _, s in chain)
                issues.append({
                    'claim': claim_num,
                    'level': 'warning',
                    'check': 'ambiguity_renyou',
                    'msg': (f"請求項{claim_num}：連用形が{len(chain)}個連続しています"
                            f"（「{surfs}」）。"
                            f"各節の係り先が不明瞭になる可能性があります。"
                            f"読点や「〜することにより」等で明示的に区切ることを検討してください。")
                })
            chain = []
        else:
            chain = []

    return issues


# ──────────────────────────────────────────────
# P2: AまたはBのC 構造
# ──────────────────────────────────────────────

# 「名詞列 + または/もしくは + 名詞列 + の + 名詞」パターン
_OR_NO_PAT = re.compile(
    r'([^\s、。]{1,20})'           # A（名詞相当）
    r'(?:または|もしくは|あるいは)'  # 並列接続詞
    r'([^\s、。]{1,20})'           # B
    r'の'                          # の
    r'([^\s、。]{1,15})',           # C
    re.UNICODE
)

def _check_or_no(claim_num: int, body: str) -> list[dict]:
    """「AまたはBのC」パターンを検出する。"""
    issues = []
    for m in _OR_NO_PAT.finditer(body):
        a, b, c = m.group(1), m.group(2), m.group(3)
        # A・Bが両方名詞的な長さ（1文字だけの助詞等を除外）
        if len(a) < 2 or len(b) < 2 or len(c) < 1:
            continue
        issues.append({
            'claim': claim_num,
            'level': 'warning',
            'check': 'ambiguity_or_no',
            'msg': (f"請求項{claim_num}：「{m.group(0)}」は"
                    f"「({a}または{b})の{c}」と「{a}または({b}の{c})」の"
                    f"2通りに解釈できます。"
                    f"括弧や語順の変更で意図を明確にしてください。")
        })
    return issues


# ──────────────────────────────────────────────
# P3: 連体修飾節の連鎖
# ──────────────────────────────────────────────

def _check_modifier_chain(claim_num: int, body: str) -> list[dict]:
    """連体修飾動詞が連続するパターンを検出する。

    「〜するXをするYをするZ」のような、修飾が多重に積み重なる構造を検出。
    体言（名詞）直前の動詞（連体形）の連続数をカウントする。
    """
    issues = []
    tokens = _tokenize(body)
    n = len(tokens)
    verb_run = 0  # 連続する連体形動詞数
    run_start_surf = ''

    for i, t in enumerate(tokens):
        form = t.get('cform', '')
        pos = t['pos']

        if pos in ('動詞', '助動詞') and '連体形' in form:
            if verb_run == 0:
                run_start_surf = t['surf']
            verb_run += 1
        elif pos == '名詞' and verb_run >= _LONG_MODIFIER_VERBS:
            issues.append({
                'claim': claim_num,
                'level': 'warning',
                'check': 'ambiguity_modifier_chain',
                'msg': (f"請求項{claim_num}：「{run_start_surf}〜{t['surf']}」付近で"
                        f"連体修飾節が{verb_run}層重なっています。"
                        f"どの動詞がどの名詞を修飾するか不明瞭になる可能性があります。")
            })
            verb_run = 0
        else:
            verb_run = 0

    return issues


# ──────────────────────────────────────────────
# P4: 二重目的語（〜を〜を）
# ──────────────────────────────────────────────

def _check_double_wo(claim_num: int, body: str) -> list[dict]:
    """「〜を〜を〜する」の二重目的語を検出する。"""
    issues = []
    tokens = _tokenize(body)
    wo_positions = []

    for i, t in enumerate(tokens):
        if t['surf'] == 'を' and t['pos'] == '助詞':
            wo_positions.append(i)
        elif t['pos'] in ('動詞',) and t.get('cform', '') not in _RENYOU_FORMS:
            # 動詞の出現で区切る
            if len(wo_positions) >= 2:
                # 「を」が2つ以上あり、その間に読点・接続助詞がないか確認
                for j in range(len(wo_positions) - 1):
                    between = tokens[wo_positions[j]+1:wo_positions[j+1]]
                    has_break = any(
                        bt['surf'] in ('、', '。') or
                        (bt['pos'] == '助詞' and bt['surf'] in _SETSUZOKU_JOSHI)
                        for bt in between
                    )
                    if not has_break:
                        # 「を」の前の名詞を取得（簡易）
                        n1 = tokens[wo_positions[j]-1]['surf'] if wo_positions[j] > 0 else '?'
                        n2 = tokens[wo_positions[j+1]-1]['surf'] if wo_positions[j+1] > 0 else '?'
                        issues.append({
                            'claim': claim_num,
                            'level': 'warning',
                            'check': 'ambiguity_double_wo',
                            'msg': (f"請求項{claim_num}：「{n1}を〜{n2}を」の"
                                    f"二重目的語があります。"
                                    f"並列（AとBを〜する）か入れ子（AをBに〜する）かを"
                                    f"明確にしてください。")
                        })
                        break
            wo_positions = []

    return issues


# ──────────────────────────────────────────────
# P5: 読点のない長文
# ──────────────────────────────────────────────

def _check_long_no_comma(claim_num: int, body: str) -> list[dict]:
    """読点なしで長く続く文節を検出する。"""
    issues = []
    # 文を「、」「。」で分割し、閾値超の節を警告
    segments = re.split(r'[、。]', body)
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= _LONG_CLAUSE_CHARS and seg:
            issues.append({
                'claim': claim_num,
                'level': 'info',
                'check': 'ambiguity_long_clause',
                'msg': (f"請求項{claim_num}：読点なしで{len(seg)}文字続く節があります"
                        f"（「{seg[:20]}…」）。"
                        f"係り受けが不明瞭になりやすいため、読点の挿入を検討してください。")
            })
    return issues


# ──────────────────────────────────────────────
# メインエントリー
# ──────────────────────────────────────────────

def check_ambiguity(claims: dict[int, str]) -> list[dict[str, Any]]:
    """全請求項に対して係り受け曖昧性チェックを実行する。

    Args:
        claims: {請求項番号: 本文テキスト}

    Returns:
        issues のリスト。各要素は dict:
            claim   : 請求項番号 (int)
            level   : 'error' | 'warning' | 'info'
            check   : チェック種別 (str)
            msg     : メッセージ (str)
    """
    issues: list[dict] = []
    for num in sorted(claims.keys()):
        body = claims[num]
        issues += _check_renyou_chain(num, body)
        issues += _check_or_no(num, body)
        issues += _check_modifier_chain(num, body)
        issues += _check_double_wo(num, body)
        issues += _check_long_no_comma(num, body)
    return issues
