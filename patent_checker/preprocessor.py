# -*- coding: utf-8 -*-
"""
前処理モジュール — フォーマット検出と正規化

J-PlatPatフォーマットと出願時フォーマットの差異を吸収し、
解析コアに統一された内部表現を渡す。
"""
import re
from enum import Enum
from dataclasses import dataclass, field


class DocFormat(Enum):
    """文書フォーマット種別"""
    JPLATPAT = "jplatpat"    # J-PlatPat公報形式
    FILING   = "filing"      # 出願時形式
    UNKNOWN  = "unknown"     # 不明（ベストエフォート）


@dataclass
class NormalizedDoc:
    """正規化済みドキュメント"""
    text: str                           # 正規化済みテキスト
    detected_format: DocFormat          # 検出されたフォーマット
    metadata: dict = field(default_factory=dict)   # メタ情報
    warnings: list = field(default_factory=list)   # 前処理中の警告


def detect_format(text: str) -> DocFormat:
    """テキストからフォーマットを自動検出する。

    J-PlatPat特有のパターン:
      - (54)【発明の名称】, (57)【要約】 等の括弧付きプレフィックス
      - 「閉じる」「開く」等のUIノイズ行
      - 【明細書】（出願時の【書類名】明細書 と異なる）

    出願時フォーマット特有のパターン:
      - 【書類名】明細書 / 【書類名】特許請求の範囲 / 【書類名】要約書
    """
    # 出願時フォーマットの判定（【書類名】が複数回出現）
    filing_markers = len(re.findall(r'【書類名】', text))
    if filing_markers >= 2:
        return DocFormat.FILING

    # J-PlatPat の判定
    jplatpat_markers = 0
    if re.search(r'\(\d+\)【', text):              # (54)【発明の名称】等
        jplatpat_markers += 1
    if re.search(r'^(閉じる|開く)\s*$', text, re.MULTILINE):  # UIノイズ
        jplatpat_markers += 1
    if re.search(r'【明細書】', text):              # 【明細書】（J-PlatPat固有）
        jplatpat_markers += 1
    if re.search(r'(詳細な説明\t|請求の範囲\t)', text):  # タブ区切りノイズ
        jplatpat_markers += 1
    if re.search(r'FI\s+[A-Z]\d{2}[A-Z]', text):  # FI分類
        jplatpat_markers += 1

    if jplatpat_markers >= 1:
        return DocFormat.JPLATPAT

    # 【書類名】が1回だけ → 出願時
    if filing_markers == 1:
        return DocFormat.FILING

    # 標準的な明細書マーカーがあれば UNKNOWN として処理
    return DocFormat.UNKNOWN


def normalize(text: str, source_format: DocFormat = None) -> NormalizedDoc:
    """テキストを統一フォーマットに正規化する。

    Args:
        text: 生テキスト
        source_format: フォーマット指定（Noneなら自動検出）

    Returns:
        NormalizedDoc: 正規化済みドキュメント
    """
    warnings = []
    metadata = {}

    if source_format is None:
        source_format = detect_format(text)

    # 共通前処理
    text = _normalize_newlines(text)

    # フォーマット固有の正規化
    if source_format == DocFormat.JPLATPAT:
        text, meta, warns = _normalize_jplatpat(text)
        metadata.update(meta)
        warnings.extend(warns)
    elif source_format == DocFormat.FILING:
        text, meta, warns = _normalize_filing(text)
        metadata.update(meta)
        warnings.extend(warns)

    return NormalizedDoc(
        text=text,
        detected_format=source_format,
        metadata=metadata,
        warnings=warnings,
    )


# ── 共通前処理 ──────────────────────────────

def _normalize_newlines(text: str) -> str:
    """改行コードを LF に統一"""
    return text.replace('\r\n', '\n').replace('\r', '\n')


# ── J-PlatPat固有の正規化 ──────────────────────────────

def _normalize_jplatpat(text: str) -> tuple:
    """J-PlatPatフォーマットの正規化

    Returns:
        (normalized_text, metadata_dict, warnings_list)
    """
    metadata = {}
    warnings = []

    # UIノイズ行の除去
    noise_lines = {'閉じる', '開く'}
    noise_tab_pats = {'詳細な説明\t', '請求の範囲\t'}
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped in noise_lines:
            continue
        if stripped in noise_tab_pats:
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned)

    # (NN)プレフィックスの除去: (54)【発明の名称】→ 【発明の名称】
    text = re.sub(r'\(\d+\)\s*【', '【', text)

    # 【明細書】→ 除去（出願時フォーマットには不要）
    text = re.sub(r'^【明細書】\s*$', '', text, flags=re.MULTILINE)

    return text, metadata, warnings


# ── 出願時フォーマット固有の正規化 ──────────────────────────────

def _normalize_filing(text: str) -> tuple:
    """出願時フォーマットの正規化

    【書類名】明細書 / 【書類名】特許請求の範囲 等の
    メタ行を処理し、セクション見出しを標準形に変換する。

    Returns:
        (normalized_text, metadata_dict, warnings_list)
    """
    metadata = {}
    warnings = []

    # 【書類名】行を検出してメタ情報として記録
    doc_names = re.findall(r'【書類名】\s*(.+)', text)
    if doc_names:
        metadata['document_names'] = doc_names

    # 【書類名】XXX → 除去（セクション見出しは別途存在するため）
    text = re.sub(r'^【書類名】.*$', '', text, flags=re.MULTILINE)

    # 連続空行の圧縮
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text, metadata, warnings
