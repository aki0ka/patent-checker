"""特許明細書チェッカー パッケージ

モジュール構成:
  preprocessor  - フォーマット検出・正規化 (DocFormat, NormalizedDoc, normalize)
  parser        - セクション分割・請求項パース (split_sections, parse_claims)
  tokenizer     - fugashi形態素解析・名詞句抽出 (_tokenize, _noun_span 等)
  analyzer      - M2-M6チェック・メイン解析 (analyze, check_zenshou 等)
  viewer        - ブロック構築・HTMLハイライト (build_blocks)
  gui           - PyWebView GUI + クリップボード監視
  cli           - CLIエントリーポイント
  mcp_server    - MCPサーバー
"""

from .preprocessor import DocFormat, NormalizedDoc, normalize, detect_format
from .analyzer import analyze, build_noun_groups

__version__ = "0.61.0"
__release_date__ = "2026-04-22"
__all__ = [
    "DocFormat",
    "NormalizedDoc",
    "normalize",
    "detect_format",
    "analyze",
    "build_noun_groups",
]
