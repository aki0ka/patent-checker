# -*- coding: utf-8 -*-
"""
特許明細書方式チェッカー - GUI/PyWebView モジュール
PyWebView ブリッジ・GUI起動を担当

入力方式:
  - ドラッグ&ドロップ (.txt / .docx / .pdf)
  - テキストエリアへのペースト → チェック実行ボタン
"""

import os
import json

try:
    import webview
    WEBVIEW_AVAILABLE = True
except Exception:
    WEBVIEW_AVAILABLE = False

from .analyzer import analyze
from .file_reader import read_file
from . import config as _cfg


# ══════════════════════════════════════════════════════════
# PyWebView API
# ══════════════════════════════════════════════════════════
class Api:
    """PyWebViewからJS経由で呼ばれるPython API"""

    # --- 解析 ---
    def run_analyze(self, text: str) -> dict:
        """テキストを解析してJSONシリアライズ可能なdictを返す"""
        if not text or not text.strip():
            return {'error': 'テキストが空です'}
        try:
            result = analyze(text)
            return json.loads(json.dumps(result, default=list))
        except Exception as e:
            import traceback
            return {'error': str(e), 'trace': traceback.format_exc()}

    # --- ファイル読み込み ---
    def read_file(self, path: str) -> dict:
        """ファイルパスからテキストを抽出する"""
        return read_file(path)

    # --- 設定 ---
    def get_config(self) -> dict:
        """現在の設定を返す"""
        return _cfg.load()

    def set_always_on_top(self, enabled: bool) -> dict:
        """常に前面表示を切り替える"""
        try:
            _cfg.set_value('always_on_top', bool(enabled))
            windows = webview.windows
            if windows:
                import threading
                def _apply():
                    try:
                        windows[0].on_top = bool(enabled)
                    except Exception:
                        pass
                threading.Thread(target=_apply, daemon=True).start()
            return {'ok': True}
        except Exception as e:
            return {'error': str(e)}

    def open_file_dialog(self) -> dict:
        """ネイティブファイルダイアログを開きファイルを読み込む"""
        try:
            windows = webview.windows
            if not windows:
                return {'error': 'ウィンドウが見つかりません'}
            result = windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=(
                    'テキストファイル (*.txt)',
                    'Word文書 (*.docx)',
                    'PDFファイル (*.pdf)',
                    '全ファイル (*.*)',
                ),
            )
            if not result or len(result) == 0:
                return {'cancelled': True}
            return read_file(result[0])
        except Exception as e:
            import traceback
            return {'error': str(e), 'trace': traceback.format_exc()}

    def save_setting(self, key: str, value) -> dict:
        """任意の設定値を保存する"""
        _allowed = {'theme', 'always_on_top', 'window_width', 'window_height'}
        if key not in _allowed:
            return {'error': f'不明な設定キー: {key}'}
        _cfg.set_value(key, value)
        return {'ok': True}


# ══════════════════════════════════════════════════════════
# GUI メイン
# ══════════════════════════════════════════════════════════
def main():
    """PyWebView GUIを起動"""
    if not WEBVIEW_AVAILABLE:
        raise ImportError('pywebview がインストールされていません: pip install pywebview')

    # 設定読み込み
    cfg = _cfg.load()

    # HTMLテンプレートパス
    module_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(module_dir, 'html_template.html')

    if not os.path.exists(html_path):
        raise FileNotFoundError(f'HTML template not found: {html_path}')

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 一時HTMLファイルを書き出す（pywebviewはfile://URLが必要）
    temp_html_path = os.path.join(os.path.dirname(module_dir), '_checker_ui.html')
    with open(temp_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    url = 'file:///' + temp_html_path.replace('\\', '/').lstrip('/')

    api = Api()

    window = webview.create_window(
        title='特許明細書チェッカー',
        url=url,
        js_api=api,
        width=cfg.get('window_width', 1440),
        height=cfg.get('window_height', 900),
        min_size=(900, 600),
        on_top=cfg.get('always_on_top', False),
    )

    def on_loaded():
        """ロード完了時: 設定をJSに渡す"""
        import time
        time.sleep(0.3)
        cfg_json = json.dumps(_cfg.load(), ensure_ascii=False)
        window.evaluate_js(f'window.applyConfig && window.applyConfig({cfg_json})')

    window.events.loaded += on_loaded

    webview.start(debug=False)

    # 終了時にウィンドウサイズを保存
    try:
        _cfg.set_value('window_width', window.width)
        _cfg.set_value('window_height', window.height)
    except Exception:
        pass

    # 一時ファイル削除
    if os.path.exists(temp_html_path):
        try:
            os.unlink(temp_html_path)
        except Exception:
            pass
