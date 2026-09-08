# -*- coding: utf-8 -*-
"""M3: 照応詞の直前に置かれた連体修飾節（「出力された前記データ」型）の検出テスト。

「前記X」は先行詞を一意に選択済みなので、その手前の連体修飾節は絞り込みとして
機能しない（再絞り込み不可）。level は info（新しい技術的事実の追加でありうるため）。
"""
from __future__ import annotations

import pytest

from meisai_checker.patent.anaphora import check_zenshou


def _pre_mod_msgs(text):
    return [i['msg'] for i in check_zenshou({1: text}, {1: []})
            if '絞り込みとして機能しない' in i['msg']]


@pytest.mark.parametrize('phrase', [
    '出力された前記データ',
    '取得した前記データ',
    '記憶される前記データ',
    '出力する前記データ',
])
def test_pre_modifier_detected(phrase):
    text = ('データを出力する出力部と、'
            f'{phrase}を記憶する記憶部とを備える、装置。')
    assert len(_pre_mod_msgs(text)) == 1, phrase


def test_pre_modifier_level_is_info():
    text = ('データを出力する出力部と、'
            '出力された前記データを記憶する記憶部とを備える、装置。')
    issues = [i for i in check_zenshou({1: text}, {1: []})
              if '絞り込みとして機能しない' in i['msg']]
    assert issues and all(i['level'] == 'info' for i in issues)


def test_pre_modifier_not_detected_for_plain_reference():
    """修飾節が無ければ出さない。"""
    text = ('データを出力する出力部と、'
            '前記データを記憶する記憶部とを備える、装置。')
    assert _pre_mod_msgs(text) == []


def test_pre_modifier_not_detected_when_head_is_later_noun():
    """「〜した前記BのC」は連体節が右側主要部Cにかかりうるため対象外。"""
    text = ('データを出力する出力部と、'
            '出力された前記データの識別子を記憶する記憶部とを備える、装置。')
    assert _pre_mod_msgs(text) == []


def test_pre_modifier_not_detected_for_plural_antecedent():
    """群として導入された先行詞は部分参照の意図がありうるため対象外。"""
    text = ('複数のデータを出力する出力部と、'
            '出力された前記データを記憶する記憶部とを備える、装置。')
    assert _pre_mod_msgs(text) == []


def test_pre_modifier_message_truncates_long_clause():
    """長い連体修飾節は照応詞に近い側30字を残して先頭を省略する。"""
    text = ('データを出力する出力部と、'
            '所定の条件が満たされた場合において所定の手順に従って逐次的に生成され'
            'かつ所定の形式に変換されて出力された前記データを記憶する記憶部とを'
            '備える、装置。')
    msgs = _pre_mod_msgs(text)
    assert len(msgs) == 1
    assert '…' in msgs[0]
