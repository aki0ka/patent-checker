# -*- coding: utf-8 -*-
"""書類構造チェック (M5)。

- check_structure: 記録項目の存在・順序・段落番号配置
- check_para_nums: 段落番号の連続性（欠番・重複・逆転）
- check_midashi_numbers: 見出しナンバー（１．…等）の順序
"""

from __future__ import annotations

import re


# ── 見出し分類テーブル ──────────────────────────────────────────

# TYPE1: 右側に記述が必要、または段落番号を置かないセクション
_HEADING_TYPE1 = {
    # 願書セクション（段落番号なし）
    '書類名', '発明の名称', '整理番号', '提出日', 'あて先',
    '国際特許分類', '住所又は居所', '氏名又は名称', '識別番号', '予納台帳番号',
    '納付金額', '電話番号', 'ファクシミリ番号',
    # 願書セクション（配下に子見出しのみ、段落番号なし）
    '発明者', '特許出願人', '代理人', '弁理士',
    '手数料の表示', '提出物件の目録', '物件名',
    '選択図',
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

_MEISHO_ITEMS = [
    ('技術分野',        '【技術分野】',                       'optional'),
    ('背景技術',        '【背景技術】',                       'optional'),
    ('先行技術文献',    '【先行技術文献】',                   'optional'),
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
    if re.match(r'^図[０-９0-9]+$', label):
        return 1  # 【図１】等は右側に説明文
    if re.match(r'^請求項[０-９0-9]+$', label):
        return 1  # 請求項は段落番号なし
    return 1  # 未知の見出し → 誤検出回避のためチェックスキップ


def check_structure(text):
    """記録項目の存在・順序・段落番号配置をチェック。
    J-PlatPat公報固有ヘッダを除外するため、
    【発明の詳細な説明】または【特許請求の範囲】以降の行のみを対象とする。
    """
    issues = []
    lines = text.splitlines()

    # 明細書本文の開始行を特定
    # 出願形式: 【書類名】　明細書 / J-PlatPat: 【発明の詳細な説明】
    start_line = 0
    for i, line in enumerate(lines):
        if re.search(r'【書類名】\s*明細書|【発明の詳細な説明】|【特許請求の範囲】', line):
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
        return int(s.translate(str.maketrans('０１２３４５６７８９', '0123456789')))

    prev1 = 0
    prev2 = 0

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if re.match(r'^【\d{4,5}】', stripped):
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
