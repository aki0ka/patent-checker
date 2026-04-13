# -*- coding: utf-8 -*-
"""
「該収容部内」照応詞エラーの診断スクリプト
Windows環境で実行して結果を教えてください。

実行方法:
  .venv\Scripts\python debug_shuyo.py
"""

from meisai_checker.tokenizer import (
    _tokenize, _collect_defined_nouns, _found_in_scope, _noun_after_zenshou
)

print("=" * 60)
print("診断: 「該収容部内」照応詞チェック")
print("=" * 60)

# 請求項内で「該収容部内」の直前に現れるはずのテキスト（先行詞を含む）
scope_text = "収容する収容部と、"
noun_to_check = "収容部内"

print(f"\n[1] スコープテキスト: 「{scope_text}」")
scope_tokens = _tokenize(scope_text)
print(f"    トークン一覧:")
for t in scope_tokens:
    print(f"      surf={t['surf']!r:10s} pos={t['pos']!r:10s} pos1={t['pos1']!r}")

defined = _collect_defined_nouns(scope_tokens)
print(f"\n[2] 定義済み名詞句: {sorted(defined)}")

result = _found_in_scope(noun_to_check, scope_tokens)
print(f"\n[3] _found_in_scope('{noun_to_check}', ...) = {result}")
print(f"    期待値: True  →  {'✓ OK' if result else '✗ NG（バグ再現）'}")

# 「該収容部内」のトークン化も確認
print("\n" + "=" * 60)
zenshou_text = "該収容部内"
print(f"[4] 照応詞テキストのトークン化: 「{zenshou_text}」")
z_tokens = _tokenize(zenshou_text)
for t in z_tokens:
    print(f"      surf={t['surf']!r:10s} pos={t['pos']!r:10s} pos1={t['pos1']!r}")

# 「該」の直後の名詞句を取得
noun_result = _noun_after_zenshou(z_tokens, 0)
print(f"\n[5] _noun_after_zenshou → 「{noun_result}」")
print(f"    期待値: 「収容部内」 →  {'✓ OK' if noun_result == '収容部内' else f'✗ NG（実際は {noun_result!r}）'}")

# より広いスコープでテスト
print("\n" + "=" * 60)
wider_scope = "収容する収容部と、収容部２０と"
print(f"[6] 広いスコープ: 「{wider_scope}」")
wider_tokens = _tokenize(wider_scope)
wider_defined = _collect_defined_nouns(wider_tokens)
print(f"    定義済み名詞句: {sorted(wider_defined)}")
result2 = _found_in_scope(noun_to_check, wider_tokens)
print(f"    _found_in_scope('{noun_to_check}', ...) = {result2}")

print("\n" + "=" * 60)
import meisai_checker
print(f"バージョン: {meisai_checker.__version__} ({meisai_checker.__release_date__})")
