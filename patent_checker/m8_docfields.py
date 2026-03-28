"""M8: 明細書記録項目チェック（特許法施行規則様式第29準拠）

JPO出願手続ガイドライン（https://www.pcinfo.jpo.go.jp/guide/DocGuide.htm）に基づき、
明細書の記録項目の必須性・順序・下位構造・番号規則を検査する。

チェック項目:
  FC1  必須項目の存在確認（【書類名】【発明の名称】）
  FC2  項目の規定順序チェック
  FC3  同一項目の重複禁止
  FC4  【発明の概要】配下の必須項目（3項目のうち1つ以上）
  FC5  【先行技術文献】の下位構造（【特許文献】or【非特許文献】）
  FC6  【特許文献○】【非特許文献○】の連続番号整合性
  FC7  【図面の簡単な説明】と【図○】の整合性
  FC8  【化○】【数○】【表○】が段落番号の外にある検出
  FC9  【実施例】の枝番禁止（【実施例１－１】等）
  FC10 段落番号の配置ルール（項目直下に必要）
  FC11 段落番号の連続性
  FC12 【発明の名称】直後チェック（書類名の次が名称でなければならない）
"""

import re
from typing import Any

# ──────────────────────────────────────────────
# 見出しパターン
# ──────────────────────────────────────────────

# 【〇〇】形式の見出しをすべて抽出
_HEADING_PAT = re.compile(r'【([^】]+)】')

# 段落番号
_PARA_NUM_PAT = re.compile(r'【([0-9０-９]{4,5})】')

# 図番号【図○】
_ZUMEN_PAT = re.compile(r'【図(\d+)】')

# 連番付き見出し（【特許文献1】【非特許文献2】【化1】【数1】【表1】【実施例1】等）
_NUMBERED_HEAD_PAT = re.compile(
    r'【(特許文献|非特許文献|化|数|表|図|実施例)([\d０-９]+(?:[－\-][\w０-９]+)*)】'
)

# 【実施例】の枝番禁止パターン （【実施例１－１】等）
_JISSIREI_BRANCH_PAT = re.compile(r'【実施例[\d０-９]+[－\-]')

# ──────────────────────────────────────────────
# 規定の項目順序（この順序で出現すべき）
# 同一レベルの任意項目も含む全リスト
# ──────────────────────────────────────────────
_SECTION_ORDER = [
    '書類名',
    '発明の名称',
    '技術分野',
    '背景技術',
    '先行技術文献',
    '特許文献',
    '非特許文献',
    '発明の概要',
    '発明が解決しようとする課題',
    '課題を解決するための手段',
    '発明の効果',
    '図面の簡単な説明',
    '発明を実施するための形態',
    # 実施例は番号付きで動的に扱う
    '産業上の利用可能性',
    '符号の説明',
    '受託番号',
    '配列表フリーテキスト',
    '配列表',
]

# 【発明の概要】の直下に必要な3項目（1つ以上必須）
_GAIYOU_CHILDREN = {
    '発明が解決しようとする課題',
    '課題を解決するための手段',
    '発明の効果',
}

# 段落番号を配下に必要とする項目
_NEEDS_PARA = {
    '技術分野', '背景技術',
    '発明が解決しようとする課題', '課題を解決するための手段', '発明の効果',
    '図面の簡単な説明', '発明を実施するための形態',
    '産業上の利用可能性', '符号の説明', '受託番号',
}

# 「条件必須」チェック用（図面添付時に【図面の簡単な説明】が必要かどうかは
# 図面の有無で判断。ここでは【図○】が本文中にあるかで代替判定）


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────

def _zenkaku_to_hankaku_num(s: str) -> str:
    """全角数字を半角数字に変換する。"""
    return s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))


def _extract_headings(text: str) -> list[tuple[str, int]]:
    """テキストから (見出し名, 開始位置) のリストを返す。"""
    return [(m.group(1), m.start()) for m in _HEADING_PAT.finditer(text)]


def _extract_para_nums(text: str) -> list[tuple[int, int]]:
    """段落番号を (数値, 開始位置) のリストで返す。全角数字も変換。"""
    result = []
    for m in _PARA_NUM_PAT.finditer(text):
        num_str = _zenkaku_to_hankaku_num(m.group(1))
        result.append((int(num_str), m.start()))
    return result


# ──────────────────────────────────────────────
# FC1: 必須項目の存在確認
# ──────────────────────────────────────────────

def _fc1_required(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    names = {h for h, _ in headings}
    for req in ['書類名', '発明の名称']:
        if req not in names:
            issues.append({
                'level': 'error', 'check': 'FC1',
                'msg': f"【{req}】が存在しません（必須項目）。"
            })
    return issues


# ──────────────────────────────────────────────
# FC2: 項目の規定順序チェック
# ──────────────────────────────────────────────

def _fc2_order(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    # 規定順序リスト内の項目だけを取り出し、順序が逆転していないか確認
    ordered = [h for h, _ in headings if h in _SECTION_ORDER]
    # 実施例○は'実施例'として扱う
    def normalize(h):
        if re.match(r'実施例\d', h):
            return '実施例'
        return h

    prev_idx = -1
    prev_name = ''
    for h in ordered:
        n = normalize(h)
        if n not in _SECTION_ORDER:
            continue
        cur_idx = _SECTION_ORDER.index(n)
        if cur_idx < prev_idx:
            issues.append({
                'level': 'error', 'check': 'FC2',
                'msg': (f"【{h}】は【{prev_name}】より前に記録すべき項目です"
                        f"（規定の順序に従ってください）。")
            })
        else:
            prev_idx = cur_idx
            prev_name = h
    return issues


# ──────────────────────────────────────────────
# FC3: 同一項目の重複禁止
# ──────────────────────────────────────────────

def _fc3_duplicate(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    seen: dict[str, int] = {}
    # 連番付き項目（実施例○等）は重複チェック対象外
    non_numbered = [
        h for h, _ in headings
        if not re.search(r'\d', h) and h not in ('特許文献', '非特許文献')
    ]
    for h in non_numbered:
        if h in seen:
            seen[h] += 1
        else:
            seen[h] = 1
    for h, cnt in seen.items():
        if cnt > 1:
            issues.append({
                'level': 'error', 'check': 'FC3',
                'msg': f"【{h}】が{cnt}回記録されています。同一項目の重複は禁止です。"
            })
    return issues


# ──────────────────────────────────────────────
# FC4: 【発明の概要】配下の必須項目
# ──────────────────────────────────────────────

def _fc4_gaiyou_children(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    names = {h for h, _ in headings}
    if '発明の概要' not in names:
        return issues
    if not (_GAIYOU_CHILDREN & names):
        issues.append({
            'level': 'error', 'check': 'FC4',
            'msg': ("【発明の概要】の配下に"
                    "【発明が解決しようとする課題】【課題を解決するための手段】【発明の効果】"
                    "のいずれも記録されていません（1つ以上必須）。")
        })
    return issues


# ──────────────────────────────────────────────
# FC5: 【先行技術文献】の下位構造
# ──────────────────────────────────────────────

def _fc5_sentou_children(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    names = {h for h, _ in headings}
    if '先行技術文献' not in names:
        return issues
    has_pat = '特許文献' in names or any(re.match(r'特許文献\d', h) for h in names)
    has_nonpat = '非特許文献' in names or any(re.match(r'非特許文献\d', h) for h in names)
    if not (has_pat or has_nonpat):
        issues.append({
            'level': 'error', 'check': 'FC5',
            'msg': ("【先行技術文献】の配下に【特許文献】または【非特許文献】が"
                    "記録されていません。")
        })
    return issues


# ──────────────────────────────────────────────
# FC6: 連番整合性（【特許文献○】【非特許文献○】【化○】【数○】【表○】）
# ──────────────────────────────────────────────

def _fc6_sequential_nums(text: str) -> list[dict]:
    """各カテゴリの連番が1から始まり連続しているか確認する。"""
    issues = []
    categories: dict[str, list[int]] = {}

    for m in _NUMBERED_HEAD_PAT.finditer(text):
        cat = m.group(1)
        num_str = _zenkaku_to_hankaku_num(m.group(2).split('－')[0].split('-')[0])
        try:
            num = int(num_str)
        except ValueError:
            continue
        categories.setdefault(cat, []).append(num)

    for cat, nums in categories.items():
        nums_sorted = sorted(nums)
        if nums_sorted[0] != 1:
            issues.append({
                'level': 'error', 'check': 'FC6',
                'msg': f"【{cat}○】の番号が1から始まっていません（最初: {nums_sorted[0]}）。"
            })
        for i in range(1, len(nums_sorted)):
            if nums_sorted[i] != nums_sorted[i-1] + 1:
                issues.append({
                    'level': 'error', 'check': 'FC6',
                    'msg': (f"【{cat}○】の番号が連続していません"
                            f"（{nums_sorted[i-1]}の次が{nums_sorted[i]}）。")
                })

    return issues


# ──────────────────────────────────────────────
# FC7: 【図面の簡単な説明】と【図○】の整合性
# ──────────────────────────────────────────────

def _fc7_zumen_consistency(text: str, headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    names = {h for h, _ in headings}

    # 【図○】が本文中にあるか
    zumen_in_text = set(int(m.group(1)) for m in _ZUMEN_PAT.finditer(text))

    # 【図面の簡単な説明】がない場合
    if zumen_in_text and '図面の簡単な説明' not in names:
        issues.append({
            'level': 'error', 'check': 'FC7',
            'msg': ("【図○】の記録がありますが【図面の簡単な説明】欄がありません"
                    "（図面を添付する場合は必須）。")
        })
        return issues

    # 【図面の簡単な説明】内の図番と本文の図番の照合
    # （簡易：説明欄に出てくる図番 vs 本文中の図番）
    if '図面の簡単な説明' in names:
        # 説明欄の図番を取得
        gaikan_pos = next(pos for h, pos in headings if h == '図面の簡単な説明')
        next_major_pos = len(text)
        for h, pos in headings:
            if pos > gaikan_pos and h in ('発明を実施するための形態', '実施例', '産業上の利用可能性'):
                next_major_pos = pos
                break
        gaikan_section = text[gaikan_pos:next_major_pos]
        zumen_in_gaikan = set(int(m.group(1)) for m in _ZUMEN_PAT.finditer(gaikan_section))

        missing_in_desc = zumen_in_text - zumen_in_gaikan
        for num in sorted(missing_in_desc):
            issues.append({
                'level': 'warning', 'check': 'FC7',
                'msg': (f"【図{num}】が本文中に使用されていますが"
                        f"【図面の簡単な説明】に記載がありません。")
            })

    return issues


# ──────────────────────────────────────────────
# FC8: 【化○】【数○】【表○】が段落番号の外にある
# ──────────────────────────────────────────────

def _fc8_block_in_para(text: str) -> list[dict]:
    """【化○】【数○】【表○】は段落番号【XXXX】の中（配下）にのみ記録可能。"""
    issues = []
    block_pat = re.compile(r'【(化|数|表)([\d０-９]+)】')

    # 段落番号の範囲を特定
    para_ranges: list[tuple[int, int]] = []
    para_starts = list(_PARA_NUM_PAT.finditer(text))
    for i, m in enumerate(para_starts):
        start = m.start()
        end = para_starts[i+1].start() if i+1 < len(para_starts) else len(text)
        para_ranges.append((start, end))

    def in_para(pos: int) -> bool:
        return any(s <= pos < e for s, e in para_ranges)

    for m in block_pat.finditer(text):
        if not in_para(m.start()):
            issues.append({
                'level': 'error', 'check': 'FC8',
                'msg': (f"【{m.group(1)}{m.group(2)}】が段落番号の外に記録されています。"
                        f"【化○】【数○】【表○】は段落番号の中にのみ記録できます。")
            })
    return issues


# ──────────────────────────────────────────────
# FC9: 【実施例】の枝番禁止
# ──────────────────────────────────────────────

def _fc9_jissirei_branch(text: str) -> list[dict]:
    issues = []
    for m in _JISSIREI_BRANCH_PAT.finditer(text):
        end = text.find('】', m.start())
        label = text[m.start():end+1] if end != -1 else m.group(0)
        issues.append({
            'level': 'error', 'check': 'FC9',
            'msg': (f"「{label}」：【実施例○】に枝番を付けることはできません"
                    f"（【実施例１】【実施例２】のように連続番号のみ使用可能）。")
        })
    return issues


# ──────────────────────────────────────────────
# FC10: 段落番号の配置ルール（必要項目直下に段落番号があるか）
# ──────────────────────────────────────────────

def _fc10_para_under_section(text: str, headings: list[tuple[str, int]]) -> list[dict]:
    """段落番号が必要な項目の直下に段落番号があるか確認する。"""
    issues = []
    heading_positions = {h: pos for h, pos in headings}

    for section in _NEEDS_PARA:
        if section not in heading_positions:
            continue
        sec_pos = heading_positions[section]
        # 次の見出しまでの範囲
        next_pos = len(text)
        for h, pos in headings:
            if pos > sec_pos:
                next_pos = pos
                break
        section_text = text[sec_pos:next_pos]
        if not _PARA_NUM_PAT.search(section_text):
            issues.append({
                'level': 'error', 'check': 'FC10',
                'msg': (f"【{section}】の配下に段落番号（【０００１】等）が"
                        f"記録されていません（必須）。")
            })
    return issues


# ──────────────────────────────────────────────
# FC11: 段落番号の連続性
# ──────────────────────────────────────────────

def _fc11_para_seq(text: str) -> list[dict]:
    issues = []
    para_nums = _extract_para_nums(text)
    for i in range(1, len(para_nums)):
        prev_num, _ = para_nums[i-1]
        cur_num, _ = para_nums[i]
        if cur_num != prev_num + 1:
            issues.append({
                'level': 'error', 'check': 'FC11',
                'msg': (f"段落番号が連続していません：【{prev_num:04d}】の次が"
                        f"【{cur_num:04d}】です（【{prev_num+1:04d}】が必要）。")
            })
    return issues


# ──────────────────────────────────────────────
# FC12: 【発明の名称】の位置（【書類名】の直後）
# ──────────────────────────────────────────────

def _fc12_name_position(headings: list[tuple[str, int]]) -> list[dict]:
    issues = []
    names_only = [h for h, _ in headings]
    # 【書類名】と【発明の名称】の両方がある場合
    if '書類名' in names_only and '発明の名称' in names_only:
        idx_sho = names_only.index('書類名')
        idx_mei = names_only.index('発明の名称')
        if idx_mei != idx_sho + 1:
            issues.append({
                'level': 'error', 'check': 'FC12',
                'msg': ("【発明の名称】は【書類名】の直後に記録してください"
                        "（現在の位置が不正です）。")
            })
    return issues


# ──────────────────────────────────────────────
# メインエントリー
# ──────────────────────────────────────────────

def check_docfields(text: str) -> list[dict[str, Any]]:
    """明細書の記録項目チェックを実行する。

    Args:
        text: 明細書全文テキスト（出願時フォーマット推奨）

    Returns:
        issues のリスト。各要素は dict:
            level  : 'error' | 'warning' | 'info'
            check  : チェック種別 (FC1〜FC12)
            msg    : メッセージ (str)
    """
    headings = _extract_headings(text)
    issues: list[dict] = []

    issues += _fc1_required(headings)
    issues += _fc2_order(headings)
    issues += _fc3_duplicate(headings)
    issues += _fc4_gaiyou_children(headings)
    issues += _fc5_sentou_children(headings)
    issues += _fc6_sequential_nums(text)
    issues += _fc7_zumen_consistency(text, headings)
    issues += _fc8_block_in_para(text)
    issues += _fc9_jissirei_branch(text)
    issues += _fc10_para_under_section(text, headings)
    issues += _fc11_para_seq(text)
    issues += _fc12_name_position(headings)

    return issues
