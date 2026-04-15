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

    def read_file_b64(self, filename: str, b64_content: str) -> dict:
        """base64エンコードされたファイル内容をデコードしてテキスト抽出する。
        D&Dでfile.pathが取得できない環境向け（pywebview制限の回避策）。
        """
        import base64, io, os
        try:
            data = base64.b64decode(b64_content)
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.docx':
                import docx as _docx
                doc = _docx.Document(io.BytesIO(data))
                lines = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        lines.append(para.text)
                return {'text': '\n'.join(lines)}
            elif ext == '.pdf':
                import pdfplumber
                pages = []
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            pages.append(t)
                if not pages:
                    return {'error': 'テキストを抽出できませんでした（スキャンPDFは非対応）'}
                return {'text': '\n'.join(pages)}
            else:
                return {'error': f'非対応の形式: {ext}'}
        except Exception as e:
            import traceback
            return {'error': str(e), 'trace': traceback.format_exc()}

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

    def open_releases_page(self) -> dict:
        """GitHubリリースページをブラウザで開く"""
        import webbrowser
        webbrowser.open('https://github.com/aki0ka/meisai-checker/releases/latest')
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

    # None や型崩れに備えて明示的に int/bool へ変換する
    win_w = int(cfg.get('window_width') or 1280)
    win_h = int(cfg.get('window_height') or 760)
    on_top = bool(cfg.get('always_on_top') or False)

    window = webview.create_window(
        title='特許明細書チェッカー',
        url=url,
        js_api=api,
        width=win_w,
        height=win_h,
        min_size=(900, 600),
        on_top=on_top,
    )

    def on_loaded():
        """ロード完了時: 設定をJSに渡す"""
        import time
        import threading
        from meisai_checker import __version__, __release_date__
        time.sleep(0.3)
        cfg = _cfg.load()
        cfg['version'] = f"{__version__} ({__release_date__})"
        cfg_json = json.dumps(cfg, ensure_ascii=False)
        window.evaluate_js(f'window.applyConfig && window.applyConfig({cfg_json})')

        def _check_update():
            try:
                import urllib.request
                import urllib.error
                url = 'https://api.github.com/repos/aki0ka/meisai-checker/releases/latest'
                req = urllib.request.Request(url, headers={'User-Agent': 'meisai-checker'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                tag = data.get('tag_name', '').lstrip('v')
                if not tag:
                    return
                def _ver(s):
                    try: return tuple(int(x) for x in s.split('.'))
                    except: return (0,)
                if _ver(tag) > _ver(__version__):
                    js_tag = json.dumps(tag)
                    window.evaluate_js(
                        f'window.showUpdateBadge && window.showUpdateBadge({js_tag})'
                    )
            except Exception:
                pass  # オフライン・タイムアウト等は無視

        threading.Thread(target=_check_update, daemon=True).start()

    window.events.loaded += on_loaded

    webview.start(debug=False)

    # 終了時にウィンドウサイズを保存（None チェック: pywebviewが None を返す場合がある）
    try:
        w = window.width
        h = window.height
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            _cfg.set_value('window_width', w)
            _cfg.set_value('window_height', h)
    except Exception:
        pass

    # 一時ファイル削除
    if os.path.exists(temp_html_path):
        try:
            os.unlink(temp_html_path)
        except Exception:
            pass
