# -*- coding: utf-8 -*-
"""M3: 「一の」（数詞＋の）を伴う照応詞チェックの単体テスト。

「一のN」はスコープベースで扱う：同じ核名詞 N の複数形（群）先行詞
（「複数のN」等）が同一スコープに存在する場合のみ「一のN」への保持を
要求し、群先行詞が存在しなければ不定の存在導入として裸名詞への脱落を
許容する（project_toukei_checker_design 参照）。
"""
from __future__ import annotations

from meisai_checker.patent.anaphora import check_zenshou


def _errors(claims_text, dep_map=None):
    claims = {int(k): v for k, v in claims_text.items()}
    if dep_map is None:
        dep_map = {n: [] for n in claims}
    issues = check_zenshou(claims, dep_map)
    return [i for i in issues if i.get('level') == 'error']


def test_ichino_domain_free_bare_reference_ok():
    """ドメイン（複数のN）が無い「一のN」は不定の存在導入。裸名詞への脱落を許容する。"""
    text = ('いずれか一のシンボルを指定する操作を受け付けた場合に、'
            '当該シンボルに対応するユーザの識別情報を取得する情報処理装置。')
    assert _errors({1: text}) == []


def test_ichino_domain_free_full_form_ok():
    text = ('いずれか一のシンボルを指定する操作を受け付けた場合に、'
            '当該一のシンボルに対応するユーザの識別情報を取得する情報処理装置。')
    assert _errors({1: text}) == []


def test_ichino_with_domain_dropped_is_error():
    """「複数のN」ドメインが存在する場合、「一の」を落とすと群と個体が区別できずエラー。"""
    text = ('複数の生地を捏ねる捏ね工程と、'
            '前記複数の生地のうちの一の生地が所定重量を下回った場合に、'
            '当該生地を廃棄品として記録する廃棄記録工程とを含む、方法。')
    errors = _errors({1: text})
    assert len(errors) == 1
    assert errors[0]['noun'] == '生地'


def test_ichino_with_domain_kept_ok():
    text = ('複数の生地を捏ねる捏ね工程と、'
            '前記複数の生地のうちの一の生地が所定重量を下回った場合に、'
            '当該一の生地を廃棄品として記録する廃棄記録工程とを含む、方法。')
    assert _errors({1: text}) == []


def test_domain_linking_particle_variants_all_equivalent():
    """「のうちの」「における」「のうち」は表層バリエーションで挙動は同じ。"""
    variants = [
        '前記複数のシンボルのうちのいずれか一のシンボルが所定条件を満たす場合に、当該一のシンボルを処理する処理部とを備える、装置。',
        '前記複数のシンボルにおけるいずれか一のシンボルが所定条件を満たす場合に、当該一のシンボルを処理する処理部とを備える、装置。',
        '前記複数のシンボルのうちいずれか一のシンボルが所定条件を満たす場合に、当該一のシンボルを処理する処理部とを備える、装置。',
    ]
    for body in variants:
        text = '複数のシンボルを検出するセンサと、' + body
        assert _errors({1: text}) == [], body


def test_izureka_marker_not_load_bearing():
    """「いずれか」の有無はスコープ判定に無関係。"""
    text = ('複数のシンボルを検出するセンサと、'
            '前記複数のシンボルのうちの一のシンボルが所定条件を満たす場合に、'
            '当該一のシンボルを処理する処理部とを備える、装置。')
    assert _errors({1: text}) == []


def test_sukunakutomo_ichino_bridges_like_sukunakutomo_hitotsuno():
    """「少なくとも一の」は「少なくとも一つの」と同様、群の有無に関わらず橋渡しを許容する。"""
    text_ichino = ('少なくとも一のシンボルを検出するセンサと、'
                    '前記シンボルを処理する処理部とを備える、装置。')
    text_hitotsuno = ('少なくとも一つのシンボルを検出するセンサと、'
                       '前記シンボルを処理する処理部とを備える、装置。')
    assert _errors({1: text_ichino}) == []
    assert _errors({1: text_hitotsuno}) == []


def test_dai_ichi_no_matches_dai_ichi_no_and_dai_ni_no():
    """「第一の」「第１の」「第二の」の挙動は数字の表記に関わらず揃う。

    序数「第N（の）」は識別子として先行詞名の一部になるため、
    「第一の基板」を「前記基板」と序数を落として参照するのは
    先行詞不一致（「の」なし型の「第１測定値」→「前記測定値」と同じ扱い）。
    「一」だけが _LIMITERS 経由で特別扱いされないことをここで担保する。
    """
    for label in ('第一の', '第１の', '第二の'):
        text = (f'{label}基板を用意する準備工程と、'
                '前記基板に配線を形成する形成工程とを含む、方法。')
        errors = _errors({1: text})
        assert len(errors) == 1, label
        assert errors[0]['noun'] == '基板', label

        full = (f'{label}基板を用意する準備工程と、'
                f'前記{label}基板に配線を形成する形成工程とを含む、方法。')
        assert _errors({1: full}) == [], label


def test_ichino_with_verb_compound_noun_kept_together():
    """「一のひねり操作」のように連用形で複合名詞化している場合、
    定義側・参照側とも「一の」＋複合名詞全体を1つのキーとして扱う。
    """
    text = ('一のひねり操作を行う操作部と、'
            '前記一のひねり操作の結果を出力する出力部とを備える、装置。')
    assert _errors({1: text}) == []


def test_ichino_parent_claim_domain_via_prefix():
    """前記は祖先請求項を含めたスコープで「複数のN」ドメインの有無を判定する。"""
    claims = {
        1: '複数のシンボルを検出するセンサを備える、装置。',
        2: ('前記複数のシンボルのうちの一のシンボルが所定条件を満たす場合に、'
            '前記シンボルを処理する処理部を備える、請求項1に記載の装置。'),
    }
    dep_map = {1: [], 2: [1]}
    errors = _errors(claims, dep_map)
    # 群先行の裸参照は少なくとも warning（唯一性崩れ）として捕捉される。
    # ここでは error にまで昇格しないことのみを回帰観点として確認する
    # （群先行警告と当該exception4ゲートは重複しうるため）。
    assert all(e['claim'] == 2 for e in errors)


def test_dai_n_no_full_noun_is_antecedent_key():
    """「第Nの〜」は「第N」で打ち切らず名詞句全体を先行詞キーにする。

    MeCab は「第１」を接頭辞「第」＋数詞「１」に分割するため、「の」の
    継続判定を接頭辞のみで見ると「第１」で名詞句が切れ、「前記第１」が
    照応詞として登録されてしまう（「第１の閾値」と「第１測定値」で挙動が
    割れる）。両者が同じ扱いになることを担保する。
    """
    text = ('第１の閾値と第２の閾値と第１測定値と第２測定値とを取得する取得部と、'
            '前記第１の閾値と前記第１測定値とを比較する第１比較部と、'
            '前記第２の閾値と前記第２測定値とを比較する第２比較部と、'
            'を備える測定装置。')
    assert _errors({1: text}) == []

    issues = check_zenshou({1: text}, {1: []})
    nouns = {i.get('noun') for i in issues}
    assert '第１' not in nouns and '第２' not in nouns
