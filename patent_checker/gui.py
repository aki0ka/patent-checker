# -*- coding: utf-8 -*-
"""
特許明細書方式チェッカー - GUI/PyWebView モジュール
PyWebView ブリッジ、クリップボード監視、GUI起動を担当
"""

import os
import re
import time
import threading
import json

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except Exception:
    PYPERCLIP_AVAILABLE = False

try:
    import webview
    WEBVIEW_AVAILABLE = True
except Exception:
    WEBVIEW_AVAILABLE = False

from .analyzer import analyze, build_noun_groups


# ══════════════════════════════════════════════════════════
# PyWebView API
# ══════════════════════════════════════════════════════════
class Api:
    """PyWebViewからJS経由で呼ばれるPython API"""

    def run_analyze(self, text):
        """テキストを解析してJSONシリアライズ可能なdictを返す"""
        if not text or not text.strip():
            return {"error": "テキストが空です"}
        try:
            result = analyze(text)
            # setをlistに変換（JSON非対応）
            return json.loads(json.dumps(result, default=list))
        except Exception as e:
            import traceback
            return {"error": str(e), "trace": traceback.format_exc()}


# ══════════════════════════════════════════════════════════
# クリップボード監視
# ══════════════════════════════════════════════════════════
class ClipboardWatcher:
    """クリップボード内容を監視し、特許文書パターンを検出してコールバックする"""

    def __init__(self, callback):
        """
        Args:
            callback: テキスト検出時に呼ばれるコールバック。callback(text)の形式
        """
        self.callback = callback
        self.pat = re.compile(
            r'【特許請求の範囲】|【請求項[０-９0-9]+】'
            r'|【発明の詳細な説明】|【発明を実施するための形態】'
        )
        self.last = ""
        self.running = False
        self.thread = None

    def start(self):
        """クリップボード監視を開始"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()
        print("[ClipboardWatcher] started", flush=True)

    def stop(self):
        """クリップボード監視を停止"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("[ClipboardWatcher] stopped", flush=True)

    def _watch(self):
        """監視ループ（スレッド内で実行）"""
        while self.running:
            try:
                if PYPERCLIP_AVAILABLE:
                    text = pyperclip.paste()
                    if text and text != self.last and self.pat.search(text):
                        self.last = text
                        print(f"[ClipboardWatcher] detected patent text ({len(text)} chars)", flush=True)
                        self.callback(text)
            except Exception as e:
                print(f"[ClipboardWatcher] error: {e}", flush=True)
            time.sleep(1.0)


def clipboard_watcher_legacy(window):
    """従来の関数形式のクリップボード監視（互換性用）

    Args:
        window: pywebview window オブジェクト
    """
    pat = re.compile(
        r'【特許請求の範囲】|【請求項[０-９0-9]+】'
        r'|【発明の詳細な説明】|【発明を実施するための形態】'
    )
    last = ""
    print("[clipboard_watcher] started", flush=True)
    while True:
        try:
            if PYPERCLIP_AVAILABLE:
                text = pyperclip.paste()
                if text and text != last and pat.search(text):
                    last = text
                    print(f"[clipboard_watcher] detected patent text ({len(text)} chars)", flush=True)
                    safe = json.dumps(text)
                    window.evaluate_js(f'window.onClipboardUpdate({safe})')
        except Exception as e:
            print(f"[clipboard_watcher] error: {e}", flush=True)
        time.sleep(1.0)


# ══════════════════════════════════════════════════════════
# GUI メイン
# ══════════════════════════════════════════════════════════
def main():
    """PyWebView GUIを起動"""
    if not WEBVIEW_AVAILABLE:
        raise ImportError("webview is not available. Install with: pip install pywebview")

    # HTMLテンプレートパスを決定（このファイルと同じディレクトリ）
    module_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(module_dir, 'html_template.html')

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML template not found: {html_path}")

    # HTMLファイルを読み込む
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 一時的なHTMLファイルを作成（デバッグしやすいように固定パス）
    temp_html_path = os.path.join(os.path.dirname(module_dir), '_checker_ui.html')
    with open(temp_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # file:// URL (Windows: file:///C:/... Linux/Mac: file:///tmp/...)
    url = 'file:///' + temp_html_path.replace('\\', '/').lstrip('/')

    # APIインスタンス
    api = Api()

    # ウィンドウ作成
    window = webview.create_window(
        title='特許明細書チェッカー',
        url=url,
        js_api=api,
        width=1440,
        height=900,
        min_size=(900, 600),
    )

    def on_loaded():
        """ウィンドウロード完了時のコールバック"""
        print(f"[on_loaded] loaded: {url}", flush=True)
        # JSが確実に初期化された後にwatcherを起動するため少し待つ
        time.sleep(0.5)
        if PYPERCLIP_AVAILABLE:
            print("[on_loaded] starting clipboard watcher", flush=True)
            t = threading.Thread(
                target=clipboard_watcher_legacy,
                args=(window,),
                daemon=True,
            )
            t.start()
        else:
            print("[on_loaded] pyperclip not available - install pyperclip", flush=True)

    window.events.loaded += on_loaded

    # GUI起動
    webview.start(debug=False)

    # クリーンアップ
    if os.path.exists(temp_html_path):
        try:
            os.unlink(temp_html_path)
        except Exception:
            pass
