# -*- coding: utf-8 -*-
"""
特許明細書チェッカー - ファイル読み込みモジュール
.txt / .docx / .pdf からテキストを抽出する
"""

from __future__ import annotations
import os


def read_file(path: str) -> dict:
    """
    ファイルパスからテキストを抽出する。

    Returns:
        {'text': str}  — 成功
        {'error': str} — 失敗
    """
    if not os.path.exists(path):
        return {'error': f'ファイルが見つかりません: {path}'}

    ext = os.path.splitext(path)[1].lower()

    try:
        if ext == '.txt':
            return _read_txt(path)
        elif ext == '.docx':
            return _read_docx(path)
        elif ext == '.pdf':
            return _read_pdf(path)
        else:
            return {'error': f'未対応の形式です: {ext}（.txt / .docx / .pdf に対応）'}
    except Exception as e:
        return {'error': f'読み込みエラー: {e}'}


def _read_txt(path: str) -> dict:
    """テキストファイルを読む。UTF-8 → CP932 の順で試みる"""
    for enc in ('utf-8', 'utf-8-sig', 'cp932', 'shift_jis'):
        try:
            with open(path, 'r', encoding=enc) as f:
                text = f.read()
            return {'text': text}
        except UnicodeDecodeError:
            continue
    return {'error': 'テキストファイルのエンコーディングを判定できませんでした'}


def _read_docx(path: str) -> dict:
    """Word文書(.docx)を読む。python-docx が必要"""
    try:
        import docx  # python-docx
    except ImportError:
        return {'error': 'python-docx が必要です: pip install python-docx'}

    doc = docx.Document(path)
    lines = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)

    if not lines:
        return {'error': '文書にテキストが見つかりませんでした'}

    return {'text': '\n'.join(lines)}


def _read_pdf(path: str) -> dict:
    """PDFファイルを読む。pdfplumber が必要。スキャンPDFは非対応"""
    try:
        import pdfplumber
    except ImportError:
        return {'error': 'pdfplumber が必要です: pip install pdfplumber'}

    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())

    if not pages_text:
        return {
            'error': (
                'PDFからテキストを抽出できませんでした。'
                'スキャン画像PDFには対応していません（テキストレイヤー付きPDFのみ対応）。'
            )
        }

    return {'text': '\n'.join(pages_text)}
