# -*- coding: utf-8 -*-
"""
「該収容部内」照応詞エラーの詳細診断 — 実際のファイル使用
実行方法:
  .venv\Scripts\python debug_shuyo2.py "特願2022-170915(P2022-170915).txt"
"""
import sys
from meisai_checker.file_reader import read_file
from meisai_checker.preprocessor import detect_and_normalize
from meisai_checker.parser import parse_sections, parse_claims
from meisai_checker.tokenizer import (
    _tokenize, _collect_defined_nouns, _found_in_scope,
    _noun_after_zenshou, _ZENSHOU_WORDS, _TOUGAI_WORDS,
)

if len(sys.argv) < 2:
    print("使い方: .venv\\Scripts\\python debug_shuyo2.py <ファイルパス>")
    sys.exit(1)

path = sys.argv[1]
print(f"ファイル: {path}")

text = read_file(path)
text = detect_and_normalize(text)
sections = parse_sections(text)
claims, dep_map = parse_claims(sections.get("claims", ""))

print(f"請求項数: {len(claims)}")

TARGET = "収容部内"
TARGET_WORD = "該"

for num in sorted(claims.keys()):
    body = claims[num]
    if TARGET_WORD + TARGET not in body and TARGET not in body:
        continue

    tokens = _tokenize(body)

    for i, t in enumerate(tokens):
        if t['surf'] not in _ZENSHOU_WORDS:
            continue
        if t['surf'] == '該' and i > 0 and tokens[i-1]['surf'] == '当':
            continue

        noun = _noun_after_zenshou(tokens, i)
        if noun != TARGET:
            continue

        print(f"\n{'='*60}")
        print(f"請求項{num}に「{t['surf']}{noun}」を発見 (トークン位置: {i})")

        scope_tokens = tokens[:i]
        defined = _collect_defined_nouns(scope_tokens)
        result = _found_in_scope(noun, scope_tokens)

        print(f"スコープ内定義済み名詞（「収容」含む語のみ表示）:")
        for d in sorted(defined):
            if '収容' in d or '部' in d:
                print(f"  「{d}」")
        print(f"全定義済み名詞数: {len(defined)}")
        print(f"_found_in_scope('{noun}', scope) = {result}")

        # スコープ最後の100文字を表示
        scope_text = ''.join(t['surf'] for t in scope_tokens)
        print(f"\nスコープ末尾100文字: 「...{scope_text[-100:]}」")

        # 請求項全体の「収容部」出現位置を確認
        print(f"\n請求項{num}内の「収容部」出現:")
        idx = 0
        while True:
            pos = body.find('収容部', idx)
            if pos < 0:
                break
            ctx = body[max(0,pos-10):pos+15]
            marker = "★前方" if pos < sum(t['end'] for t in tokens[:i])//len(tokens[:i])*i else "（後方）"
            print(f"  pos={pos}: 「...{ctx}...」")
            idx = pos + 1
