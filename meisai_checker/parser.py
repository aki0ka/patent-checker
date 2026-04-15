# -*- coding: utf-8 -*-
"""
パーサーモジュール — 明細書のセクション分割・請求項解析

テキストをセクション（特許請求の範囲、発明の詳細な説明等）に分割し、
請求項の番号・本文・従属関係・種別を解析する。
"""
import re


def z2h(s):
    """全角数字・英字→半角"""
    result = []
    for c in s:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        else:
            result.append(c)
    return ''.join(result)


def from_bytes(data):
    for enc in ["utf-8-sig", "utf-8", "shift_jis", "cp932", "euc-jp"]:
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


SECTION_PATTERNS = {
    "title":       r"【発明の名称】",
    "claims":      r"【特許請求の範囲】",
    "drawings":    r"【図面の簡単な説明】",
    # 「発明の詳細な説明」「発明を実施するための形態」両方を description に
    "description": r"【発明の詳細な説明】|【発明を実施するための形態】|【発明を実施するための最良の形態】|【発明の実施の形態】|【実施例】",
    "abstract":    r"【要約】|【書類名】[\s　]*要約書",
}


def split_sections(text):
    """
    【セクション名】でテキストを分割。
    同一キーに複数のセクションが対応する場合（descriptionなど）は追記する。
    """
    sections = {}
    current_key = None
    current_lines = []

    def flush():
        if current_key and current_lines:
            existing = sections.get(current_key, "")
            new_text = "\n".join(current_lines)
            sections[current_key] = (existing + "\n" + new_text).strip()

    for line in text.splitlines():
        matched = False
        for key, pat in SECTION_PATTERNS.items():
            if re.search(pat, line):
                flush()
                current_key = key
                current_lines = [line]
                matched = True
                break
        if not matched and current_key:
            current_lines.append(line)

    flush()
    return sections


def parse_claims(text):
    """請求項テキストを番号→本文の辞書に分解する。
    最大番号の請求項は「。」で終端し、それ以降のノイズ（詳細な説明等）を除去する。
    """
    claims = {}
    for m in re.finditer(
            r'【請求項([０-９0-9]+)】(.*?)(?=【請求項[０-９0-9]+】|【[^０-９0-9]|$)',
            text, re.DOTALL):
        num  = int(z2h(m.group(1)))
        body = m.group(2).strip()
        # 最初の「。」で切り捨て（それ以降は次請求項との間のノイズ）
        kuten = body.find('。')
        if kuten >= 0:
            body = body[:kuten + 1]
        claims[num] = body
    if not claims:
        for m in re.finditer(
                r'^\s*(\d+)\.\s+(.*?)(?=^\s*\d+\.\s|\Z)',
                text, re.MULTILINE | re.DOTALL):
            body = m.group(2).strip()
            kuten = body.find('。')
            if kuten >= 0:
                body = body[:kuten + 1]
            claims[int(m.group(1))] = body
    return claims


def parse_dependencies(claim_text):
    """従属先番号リスト（全角数字対応・範囲展開・省略形対応）

    対応パターン:
      請求項１又は４       → [1, 4]  ← 省略形（「請求項」を省略）
      請求項１又は請求項４  → [1, 4]
      請求項１、２又は４   → [1, 2, 4]
      請求項１〜３         → [1, 2, 3]
    """
    text = z2h(claim_text)
    deps = set()

    # 範囲展開: 請求項N〜M / 請求項NからM / 請求項N乃至M
    for m in re.finditer(
            r'請求項(\d+)\s*(?:〜|～|乃至|から)\s*(?:請求項)?(\d+)', text):
        deps |= set(range(int(m.group(1)), int(m.group(2)) + 1))

    # 接続詞をカンマに正規化
    text2 = re.sub(r'又は|または|もしくは|若しくは', ',', text)

    # 「請求項N,M,L,...」パターン（省略形を含む）
    # 「請求項」に続く最初の数字から、カンマ区切りで続く数字群（「請求項」は任意）を全て取得
    for m in re.finditer(
            r'請求項\s*(\d+(?:\s*[,、]\s*(?:請求項\s*)?\d+)*)',
            text2):
        for nm in re.finditer(r'\d+', m.group(1)):
            deps.add(int(nm.group()))

    return sorted(deps)


def extract_invention_type(claim_text):
    """請求項末尾の名詞句（発明の種類）
    「…請求項Nに記載のXXX。」形式にも対応。
    J-PlatPat形式の末尾ノイズ（詳細な説明等）も除去。
    """
    text = claim_text.strip()
    # 「。」以降のノイズ（詳細な説明\t等）を除去
    m_end = re.search(r'。', text)
    if m_end:
        text = text[:m_end.end()].strip()
    # パターン1：「に記載の〈発明種類〉。」
    m = re.search(
        r'に記載の([\u4E00-\u9FFF\u30A0-\u30FF\uFF21-\uFF5A]+)。?\s*$', text)
    if m:
        return m.group(1)
    # パターン2：末尾の漢字・カタカナ・全角英字の連続
    m = re.search(
        r'([\u4E00-\u9FFF\u30A0-\u30FF\uFF21-\uFF5A]+)。?\s*$', text)
    return m.group(1) if m else "不明"


KIND_INDEPENDENT = "独立"
KIND_SINGLE_DEP  = "単項従属"
KIND_MULTI       = "マルチクレーム"
KIND_MULTI_MULTI = "マルチマルチ"


def classify_claims(claims, dep_map):
    kinds = {}
    for num in sorted(claims.keys()):
        deps = dep_map.get(num, [])
        if   len(deps) == 0: kinds[num] = KIND_INDEPENDENT
        elif len(deps) == 1: kinds[num] = KIND_SINGLE_DEP
        else:                kinds[num] = KIND_MULTI
    # マルチマルチ判定
    for num in sorted(claims.keys()):
        if kinds[num] != KIND_MULTI:
            continue
        for d in dep_map.get(num, []):
            if kinds.get(d) == KIND_MULTI:
                kinds[num] = KIND_MULTI_MULTI
                break
    return kinds


def check_dependency(claims, dep_map, kinds):
    """M2: 従属関係チェック（自己引用・前方引用・存在チェック・マルチマルチ）"""
    issues = []

    for num in sorted(claims.keys()):
        deps = dep_map.get(num, [])
        # 自己引用
        if num in deps:
            issues.append({
                "claim": num, "level": "error",
                "msg": f"請求項{num}が自身を引用しています（特施規24条の3第2号）"
            })
        for d in deps:
            # 前方引用チェック
            if d >= num:
                issues.append({
                    "claim": num, "level": "error",
                    "msg": f"請求項{num}：請求項{d}はまだ記載されていません（前方引用）（特施規24条の3第4号）"
                })
            # 存在しない請求項
            if d not in claims:
                issues.append({
                    "claim": num, "level": "error",
                    "msg": f"請求項{num}：引用先の請求項{d}が存在しません"
                })
        # マルチマルチ
        if kinds.get(num) == KIND_MULTI_MULTI:
            multi_parents = [d for d in deps if kinds.get(d) == KIND_MULTI]
            issues.append({
                "claim": num, "level": "error",
                "msg": (f"請求項{num}：マルチマルチクレームです。"
                        f"請求項{multi_parents}はマルチクレームです。"
                        f"令和4年4月以降の出願は禁止（特施規24条の3第5号）")
            })
    return issues
