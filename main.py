"""特許明細書チェッカー エントリーポイント

引数なし → GUIを起動
引数あり → CLIとして動作
"""
import sys

if len(sys.argv) > 1:
    from patent_checker.cli import main
else:
    from patent_checker.gui import main

main()
