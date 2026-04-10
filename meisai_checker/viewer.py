# -*- coding: utf-8 -*-
"""
特許明細書方式チェッカー - ビューア/ブロック構築モジュール
ブロック構築・HTMLハイライト機能を analyzer.py からの再エクスポート
"""

from .analyzer import build_blocks, _highlight_claim, _highlight_para

__all__ = ['build_blocks', '_highlight_claim', '_highlight_para']
