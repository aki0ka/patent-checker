# -*- coding: utf-8 -*-
"""
特許明細書チェッカー - 設定管理モジュール
~/.patent-checker/config.json に設定を保存・読み込みする
"""

from __future__ import annotations
import os
import json

_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.patent-checker')
_CONFIG_FILE = os.path.join(_CONFIG_DIR, 'config.json')

_DEFAULTS: dict = {
    'always_on_top': False,
    'theme': 'light',
    'window_width': 1440,
    'window_height': 900,
}


def load() -> dict:
    """設定ファイルを読み込む。存在しない項目はデフォルト値で補完する"""
    config = dict(_DEFAULTS)
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            # 既知キーのみ採用（Noneや型不一致はデフォルト値で上書き）
            for k in _DEFAULTS:
                if k in saved and saved[k] is not None:
                    # 数値項目は int/float に強制変換して型崩れを防ぐ
                    default_val = _DEFAULTS[k]
                    try:
                        if isinstance(default_val, bool):
                            config[k] = bool(saved[k])
                        elif isinstance(default_val, int):
                            config[k] = int(saved[k])
                        elif isinstance(default_val, float):
                            config[k] = float(saved[k])
                        else:
                            config[k] = saved[k]
                    except (ValueError, TypeError):
                        pass  # 変換失敗はデフォルト値を維持
    except Exception:
        pass  # 読めなければデフォルトで続行
    return config


def save(config: dict) -> None:
    """設定をファイルに書き込む"""
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 保存失敗は無視


def get(key: str, default=None):
    """単一設定値を取得する"""
    return load().get(key, default)


def set_value(key: str, value) -> None:
    """単一設定値を更新して保存する"""
    config = load()
    config[key] = value
    save(config)
