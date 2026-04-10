"""M9: 特許願（願書）記録項目チェック（特許法施行規則様式第26準拠）

JPO出願手続ガイドラインに基づき、特許願の記録項目の必須性・
形式・下位構造を検査する。

対象: 通常出願（国と国以外の者の共有・パリ優先権・新規性喪失例外等を除く基本出願）

チェック項目:
  GA1  必須項目の存在確認（【書類名】特許願・【あて先】・【発明者】・
                            【特許出願人】・【提出物件の目録】）
  GA2  【書類名】の値が「特許願」か
  GA3  【あて先】の値が「特許庁長官殿」か
  GA4  【発明者】ブロックごとに【住所又は居所】と【氏名】が存在するか
  GA5  【特許出願人】ブロックの条件必須チェック
       （識別番号なし → 住所又は居所が必要、氏名又は名称は常に必須）
  GA6  識別番号の桁数チェック（9桁）
  GA7  【代理人】があれば識別番号と氏名又は名称が存在するか
  GA8  【整理番号】の形式チェック（10字以下、大文字ローマ字/数字/ハイフンのみ）
  GA9  【国際特許分類】の形式チェック（IPC記号フォーマット）
  GA10 【提出物件の目録】の必須物件確認（明細書・特許請求の範囲・要約書）
  GA11 【手数料の表示】の条件必須チェック（支払手段と必須フィールドの整合）
  GA12 【持分】の形式チェック（○／○、最大3桁/3桁、小数点不可）
"""

import re
from typing import Any

# ──────────────────────────────────────────────
# パーサー：【KEY】VALUE 形式のブロックを解析
# ──────────────────────────────────────────────

_HEADING_PAT = re.compile(r'【([^】]+)】[ \u3000]*(.*)')


def _parse_blocks(text: str) -> list[tuple[str, str, int]]:
    """テキストから (key, value, line_no) のリストを返す。
    インデントは無視してフラットに返す。
    """
    blocks = []
    for i, line in enumerate(text.splitlines(), 1):
        m = _HEADING_PAT.match(line.strip())
        if m:
            blocks.append((m.group(1), m.group(2).strip(), i))
    return blocks


def _extract_gansho_section(text: str) -> str:
    """全体テキストから特許願ブロックだけを切り出す。

    「【書類名】特許願」で始まり、次の「【書類名】」で終わる範囲を返す。
    見つからない場合はテキスト全体を返す。
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.search(r'【書類名】\s*特許願', line):
            start = i
            break
    if start is None:
        return text  # 願書部分が見当たらない場合はそのまま

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.search(r'【書類名】', lines[i]) and not re.search(r'特許願', lines[i]):
            end = i
            break
    return '\n'.join(lines[start:end])


def _group_by_key(blocks: list[tuple[str, str, int]], key: str) -> list[list[tuple[str, str, int]]]:
    """同名keyで区切られたブロックグループのリストを返す。

    例: 発明者が2名の場合、[発明者グループ1, 発明者グループ2] を返す。
    """
    groups = []
    current: list[tuple[str, str, int]] = []
    in_group = False
    for k, v, ln in blocks:
        if k == key:
            if in_group:
                groups.append(current)
            current = [(k, v, ln)]
            in_group = True
        elif in_group:
            # 同レベルの別の主要ブロックが始まったら終了
            major_keys = {'発明者', '特許出願人', '代理人', '手数料の表示',
                          '提出物件の目録', '書類名', 'あて先', '国際特許分類',
                          '整理番号', '提出日'}
            if k in major_keys:
                groups.append(current)
                in_group = False
                current = []
                # 次の主要キーの処理（再帰不要）
                if k == key:
                    current = [(k, v, ln)]
                    in_group = True
            else:
                current.append((k, v, ln))
    if in_group and current:
        groups.append(current)
    return groups


def _has_key(group: list[tuple[str, str, int]], key: str) -> bool:
    return any(k == key for k, _, _ in group)


def _get_value(group: list[tuple[str, str, int]], key: str) -> str:
    for k, v, _ in group:
        if k == key:
            return v
    return ''


# ──────────────────────────────────────────────
# GA1: 必須項目の存在確認
# ──────────────────────────────────────────────

_REQUIRED_KEYS = ['書類名', 'あて先', '発明者', '特許出願人', '提出物件の目録']

def _ga1_required(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    keys_present = {k for k, _, _ in blocks}
    for req in _REQUIRED_KEYS:
        if req not in keys_present:
            issues.append({
                'level': 'error', 'check': 'GA1',
                'msg': f"【{req}】が存在しません（特許願の必須項目）。"
            })
    return issues


# ──────────────────────────────────────────────
# GA2: 【書類名】の値チェック
# ──────────────────────────────────────────────

def _ga2_shurui(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == '書類名':
            if v and '特許願' not in v:
                issues.append({
                    'level': 'error', 'check': 'GA2',
                    'msg': f"【書類名】の値が「特許願」ではありません（現在: 「{v}」）。"
                })
            break
    return issues


# ──────────────────────────────────────────────
# GA3: 【あて先】の値チェック
# ──────────────────────────────────────────────

def _ga3_atetsaki(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == 'あて先':
            if v and '特許庁長官殿' not in v:
                issues.append({
                    'level': 'warning', 'check': 'GA3',
                    'msg': f"【あて先】は「特許庁長官殿」と記録します（現在: 「{v}」）。"
                })
            break
    return issues


# ──────────────────────────────────────────────
# GA4: 【発明者】ブロックの構造チェック
# ──────────────────────────────────────────────

def _ga4_hatsumei_sha(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    groups = _group_by_key(blocks, '発明者')
    if not groups:
        return issues  # GA1で検出済み

    for i, grp in enumerate(groups, 1):
        if not _has_key(grp, '住所又は居所'):
            issues.append({
                'level': 'error', 'check': 'GA4',
                'msg': f"発明者{i}：【住所又は居所】が記録されていません（必須）。"
            })
        if not _has_key(grp, '氏名'):
            issues.append({
                'level': 'error', 'check': 'GA4',
                'msg': f"発明者{i}：【氏名】が記録されていません（必須）。"
            })
    return issues


# ──────────────────────────────────────────────
# GA5: 【特許出願人】ブロックの条件必須チェック
# ──────────────────────────────────────────────

def _ga5_shutsugannin(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    groups = _group_by_key(blocks, '特許出願人')
    if not groups:
        return issues

    for i, grp in enumerate(groups, 1):
        has_id      = _has_key(grp, '識別番号')
        has_address = _has_key(grp, '住所又は居所')
        has_name    = _has_key(grp, '氏名又は名称')

        # 識別番号がない場合は住所が必要
        if not has_id and not has_address:
            issues.append({
                'level': 'error', 'check': 'GA5',
                'msg': (f"特許出願人{i}：【識別番号】がない場合は"
                        f"【住所又は居所】が必須です。")
            })
        # 氏名又は名称は常に必須
        if not has_name:
            issues.append({
                'level': 'error', 'check': 'GA5',
                'msg': f"特許出願人{i}：【氏名又は名称】が記録されていません（必須）。"
            })

    return issues


# ──────────────────────────────────────────────
# GA6: 識別番号の桁数チェック（9桁）
# ──────────────────────────────────────────────

_ID_NUM_PAT = re.compile(r'^[0-9０-９]{9}$')

def _zenkaku_to_han(s: str) -> str:
    return s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))

def _ga6_shikibetsu(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == '識別番号' and v:
            normalized = _zenkaku_to_han(v.replace(' ', '').replace('\u3000', ''))
            if not re.fullmatch(r'\d{9}', normalized):
                issues.append({
                    'level': 'error', 'check': 'GA6',
                    'msg': (f"【識別番号】「{v}」は9桁の番号で記録してください"
                            f"（現在 {len(normalized)} 桁）。")
                })
    return issues


# ──────────────────────────────────────────────
# GA7: 【代理人】ブロックの構造チェック
# ──────────────────────────────────────────────

def _ga7_dairi_nin(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    groups = _group_by_key(blocks, '代理人')
    if not groups:
        return issues  # 代理人は任意

    for i, grp in enumerate(groups, 1):
        has_id      = _has_key(grp, '識別番号')
        has_address = _has_key(grp, '住所又は居所')
        has_name    = _has_key(grp, '氏名又は名称')

        if not has_id:
            issues.append({
                'level': 'error', 'check': 'GA7',
                'msg': f"代理人{i}：【識別番号】が記録されていません（必須）。"
            })
        # 識別番号がない場合は住所が必要
        if not has_id and not has_address:
            issues.append({
                'level': 'error', 'check': 'GA7',
                'msg': (f"代理人{i}：【識別番号】がない場合は"
                        f"【住所又は居所】が必須です。")
            })
        if not has_name:
            issues.append({
                'level': 'error', 'check': 'GA7',
                'msg': f"代理人{i}：【氏名又は名称】が記録されていません（必須）。"
            })
    return issues


# ──────────────────────────────────────────────
# GA8: 【整理番号】の形式チェック
# ──────────────────────────────────────────────

# 大文字ローマ字・アラビア数字・ハイフン（負記号）のみ、10字以下
_SEIRI_PAT = re.compile(r'^[A-Z0-9\-]{1,10}$')

def _ga8_seiri_ban(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == '整理番号' and v:
            # 全角英数字を半角に変換して検査
            han = v.replace('\u3000', '').replace(' ', '')
            han = han.translate(str.maketrans(
                'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
                '０１２３４５６７８９－',
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                '0123456789-'
            ))
            if not _SEIRI_PAT.match(han):
                issues.append({
                    'level': 'error', 'check': 'GA8',
                    'msg': (f"【整理番号】「{v}」の形式が不正です。"
                            f"大文字ローマ字・アラビア数字・ハイフンのみ、10字以下で記録してください。")
                })
    return issues


# ──────────────────────────────────────────────
# GA9: 【国際特許分類】の形式チェック
# ──────────────────────────────────────────────

# IPC: セクション(1)+クラス(2)+サブクラス(1)+メイングループ(1-4)+/+サブグループ(2-6)
# 例: A01B   1/00  または A01B   1/999999
_IPC_LINE_PAT = re.compile(
    r'^[A-HＡ-Ｈ]'              # セクション（1桁）
    r'[0-9０-９]{2}'             # クラス（2桁）
    r'[A-ZＡ-Ｚ]'              # サブクラス（1桁）
    r'[ \u3000]+'                # スペース
    r'[0-9０-９]{1,4}'           # メイングループ
    r'/'                         # セパレータ
    r'[0-9０-９]{2,6}$'          # サブグループ
)

def _ga9_ipc(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == '国際特許分類' and v:
            # 複数行対応のため値を行に分割して各行をチェック
            for sub in v.splitlines():
                sub = sub.strip()
                if not sub:
                    continue
                if not _IPC_LINE_PAT.match(sub):
                    issues.append({
                        'level': 'warning', 'check': 'GA9',
                        'msg': (f"【国際特許分類】「{sub}」の形式を確認してください。"
                                f"例: 「Ａ０１Ｂ　　　１／００」（セクション・クラス・"
                                f"サブクラス・メイングループ・サブグループ）。")
                    })
    return issues


# ──────────────────────────────────────────────
# GA10: 【提出物件の目録】の必須物件確認
# ──────────────────────────────────────────────

_REQUIRED_BUTSUKENS = ['明細書', '特許請求の範囲', '要約書']

def _ga10_mokuroku(text: str, blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    keys = {k for k, _, _ in blocks}
    if '提出物件の目録' not in keys:
        return issues  # GA1で検出済み

    # 【物件名】の値を収集
    butsukens = [v for k, v, _ in blocks if k == '物件名']
    butsukens_text = ' '.join(butsukens)

    for req in _REQUIRED_BUTSUKENS:
        if req not in butsukens_text:
            issues.append({
                'level': 'error', 'check': 'GA10',
                'msg': (f"【提出物件の目録】に「{req}」が記録されていません（必須）。"
                        f"【物件名】{req}　１ として記録してください。")
            })
    return issues


# ──────────────────────────────────────────────
# GA11: 【手数料の表示】の条件必須チェック
# ──────────────────────────────────────────────

# 支払手段と必要フィールドの対応
# 予納: 予納台帳番号 + 納付金額
# 口座振替: 振替番号 + 納付金額
# クレジット: 指定立替納付 + 納付金額
# 電子現金納付: 納付番号のみ（納付金額不可）
# 現金納付: 納付書番号のみ（納付金額不可）

def _ga11_tesuryo(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    keys = {k for k, _, _ in blocks}
    if '手数料の表示' not in keys:
        return issues  # 任意項目

    payment_keys = {'予納台帳番号', '振替番号', '指定立替納付', '納付番号', '納付書番号'}
    has_payment = keys & payment_keys
    has_kinugaku = '納付金額' in keys

    if not has_payment:
        issues.append({
            'level': 'error', 'check': 'GA11',
            'msg': ("【手数料の表示】がありますが、支払手段"
                    "（【予納台帳番号】【振替番号】【指定立替納付】"
                    "【納付番号】【納付書番号】のいずれか）が記録されていません。")
        })
        return issues

    # 電子現金納付・現金納付は納付金額不可
    if ('納付番号' in keys or '納付書番号' in keys) and has_kinugaku:
        issues.append({
            'level': 'error', 'check': 'GA11',
            'msg': ("電子現金納付（【納付番号】）または現金納付（【納付書番号】）の場合、"
                    "【納付金額】は記録できません。")
        })

    # 予納・振替・クレジットは納付金額が必要
    if ({'予納台帳番号', '振替番号', '指定立替納付'} & keys) and not has_kinugaku:
        issues.append({
            'level': 'error', 'check': 'GA11',
            'msg': ("予納・口座振替・クレジットカード決済の場合、"
                    "【納付金額】を記録してください（アラビア数字のみ、「円」「，」不可）。")
        })

    # 納付金額の形式チェック（数字のみ）
    for k, v, _ in blocks:
        if k == '納付金額' and v:
            clean = _zenkaku_to_han(v.replace(' ', '').replace('\u3000', ''))
            if not re.fullmatch(r'\d+', clean):
                issues.append({
                    'level': 'error', 'check': 'GA11',
                    'msg': (f"【納付金額】「{v}」はアラビア数字のみで記録してください"
                            f"（「円」「，」等は不可）。")
                })

    return issues


# ──────────────────────────────────────────────
# GA12: 【持分】の形式チェック
# ──────────────────────────────────────────────

# ○／○形式、最大3桁/3桁、小数点不可
_MOCHIWAKE_PAT = re.compile(r'^[0-9０-９]{1,3}[／/][0-9０-９]{1,3}$')

def _ga12_mochiwake(blocks: list[tuple[str, str, int]]) -> list[dict]:
    issues = []
    for k, v, ln in blocks:
        if k == '持分' and v:
            clean = v.replace(' ', '').replace('\u3000', '')
            if not _MOCHIWAKE_PAT.match(clean):
                issues.append({
                    'level': 'error', 'check': 'GA12',
                    'msg': (f"【持分】「{v}」の形式が不正です。"
                            f"「○／○」（最大3桁/3桁）で記録してください"
                            f"（小数点は使用不可）。")
                })
    return issues


# ──────────────────────────────────────────────
# メインエントリー
# ──────────────────────────────────────────────

def check_gansho(text: str) -> list[dict[str, Any]]:
    """特許願（願書）の記録項目チェックを実行する。

    Args:
        text: 特許願のテキスト全文。
              出願書類一式（願書＋明細書＋…）が含まれる場合も
              願書部分を自動抽出して検査する。

    Returns:
        issues のリスト。各要素は dict:
            level  : 'error' | 'warning'
            check  : チェック種別 (GA1〜GA12)
            msg    : メッセージ (str)
    """
    # 願書部分だけを抽出
    gansho_text = _extract_gansho_section(text)

    # 【書類名】が存在しない場合（願書でないテキスト）
    if '書類名' not in gansho_text and '発明者' not in gansho_text:
        return [{
            'level': 'warning', 'check': 'GA0',
            'msg': ("特許願の記録項目が見つかりません。"
                    "「【書類名】特許願」で始まる願書テキストを入力してください。")
        }]

    blocks = _parse_blocks(gansho_text)
    issues: list[dict] = []

    issues += _ga1_required(blocks)
    issues += _ga2_shurui(blocks)
    issues += _ga3_atetsaki(blocks)
    issues += _ga4_hatsumei_sha(blocks)
    issues += _ga5_shutsugannin(blocks)
    issues += _ga6_shikibetsu(blocks)
    issues += _ga7_dairi_nin(blocks)
    issues += _ga8_seiri_ban(blocks)
    issues += _ga9_ipc(blocks)
    issues += _ga10_mokuroku(gansho_text, blocks)
    issues += _ga11_tesuryo(blocks)
    issues += _ga12_mochiwake(blocks)

    return issues
