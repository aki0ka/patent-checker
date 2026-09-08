# -*- coding: utf-8 -*-
"""TC6: 意味重複チェックの表記違い（漢字／ひらがな）を取りこぼさないこと。

方針は Word の文章校正（重ね言葉）に揃える。法令が用いている表現でも
重複は重複として指摘する（特許法36条5項「各請求項ごとに」等）。
"""
from __future__ import annotations

import pytest

from meisai_checker.textcheck.redundant import check_redundant


def _msgs(text):
    sections = {'claims': '【請求項１】\n' + text + '。'}
    return [i['msg'] for i in check_redundant(sections)]


@pytest.mark.parametrize('text', [
    '各センサ毎に測定する',          # 従来から検出
    '各医師ごとに集計する',          # ひらがな
    '各前記医師ごとの実績',          # ひらがな＋助詞「の」
    '各画素ごと算出する',            # 助詞の省略
    '各請求項ごとに記載する',        # 特許法36条5項の言い回しでも指摘する
    'およそ５ｍｍ程度',              # 約 のひらがな
    'あらかじめ事前に設定する',      # 予め のひらがな
    '先ず始めに実行する',            # まず／初め の表記違い
    '再度くり返す',                  # 繰り返 のひらがな
])
def test_redundant_detected(text):
    assert _msgs(text), text


@pytest.mark.parametrize('text', [
    '各社毎年実施する',      # 「毎年」は複合語であって重複ではない
    '各値毎年更新する',
    '毎年各社が実施する',    # 語順が逆
    '各センサの値を取得する',
    '各人ごとき者',          # 「ごとき」（如き）
])
def test_redundant_not_detected(text):
    assert _msgs(text) == [], text
