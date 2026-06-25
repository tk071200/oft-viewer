#!/usr/bin/env python3
"""
OFT Viewer - ローカルWebサーバー
使い方: python3 oft_viewer.py
ブラウザで http://localhost:8080 を開く
"""

import http.server
import json
import os
import sys
import tempfile
import urllib.parse
from io import BytesIO

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OFT ビューワー</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
    background: #F5F5F3;
    color: #1a1a1a;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 3rem 1rem;
  }
  h1 {
    font-size: 22px;
    font-weight: 600;
    margin-bottom: 0.4rem;
    letter-spacing: -0.02em;
  }
  .subtitle {
    font-size: 14px;
    color: #888;
    margin-bottom: 2.5rem;
  }
  .container { width: 100%; max-width: 680px; }
  .drop-zone {
    border: 1.5px dashed #ccc;
    border-radius: 16px;
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    background: #fff;
    transition: border-color 0.15s, background 0.15s;
  }
  .drop-zone:hover, .drop-zone.drag-over {
    border-color: #555;
    background: #fafafa;
  }
  .drop-zone .icon { font-size: 40px; margin-bottom: 0.75rem; }
  .drop-zone p { font-size: 15px; color: #444; }
  .drop-zone small { font-size: 13px; color: #aaa; }
  #file-input { display: none; }

  .spinner {
    display: none;
    margin: 2rem auto;
    width: 32px; height: 32px;
    border: 3px solid #eee;
    border-top-color: #555;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .result { display: none; margin-top: 1.5rem; }
  .card {
    background: #fff;
    border: 0.5px solid #e0e0e0;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }
  .field-label {
    font-size: 11px;
    font-weight: 600;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 4px;
  }
  .field-value {
    font-size: 15px;
    color: #1a1a1a;
    margin-bottom: 1.25rem;
    word-break: break-word;
  }
  .field-value:last-child { margin-bottom: 0; }
  .body-wrap {
    background: #F5F5F3;
    border-radius: 10px;
    padding: 1.25rem;
    font-size: 14px;
    line-height: 1.8;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 480px;
    overflow-y: auto;
    color: #2a2a2a;
  }
  .actions {
    display: flex;
    gap: 10px;
    margin-top: 1rem;
    flex-wrap: wrap;
  }
  button {
    padding: 9px 18px;
    border-radius: 8px;
    border: 0.5px solid #ccc;
    background: #fff;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.1s;
  }
  button:hover { background: #f5f5f3; }
  button.primary {
    background: #1a1a1a;
    color: #fff;
    border-color: #1a1a1a;
  }
  button.primary:hover { background: #333; }
  .error {
    background: #FEF2F2;
    color: #991B1B;
    border: 0.5px solid #FCA5A5;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    font-size: 14px;
    margin-top: 1rem;
    display: none;
  }
</style>
</head>
<body>
<div class="container">
  <h1>📧 OFT ビューワー</h1>
  <p class="subtitle">.oft ファイルをアップロードしてメールの中身を確認</p>

  <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
    <div class="icon">📂</div>
    <p>OFTファイルをここにドロップ</p>
    <small>またはクリックしてファイルを選択（.oft）</small>
  </div>
  <input type="file" id="file-input" accept=".oft,.msg">

  <div class="spinner" id="spinner"></div>
  <div class="error" id="error"></div>

  <div class="result" id="result">
    <div class="card">
      <div class="field-label">件名</div>
      <div class="field-value" id="out-subject"></div>
      <div class="field-label">差出人</div>
      <div class="field-value" id="out-from"></div>
      <div class="field-label">宛先</div>
      <div class="field-value" id="out-to"></div>
    </div>
    <div class="card">
      <div class="field-label">本文</div>
      <div class="body-wrap" id="out-body"></div>
    </div>
    <div class="actions">
      <button class="primary" onclick="copyBody()">📋 本文をコピー</button>
      <button onclick="reset()">別のファイルを開く</button>
    </div>
  </div>
</div>

<script>
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) uploadFile(fileInput.files[0]); });

function showError(msg) {
  const el = document.getElementById('error');
  el.textContent = msg;
  el.style.display = 'block';
  document.getElementById('spinner').style.display = 'none';
  document.getElementById('result').style.display = 'none';
}

function uploadFile(file) {
  document.getElementById('error').style.display = 'none';
  document.getElementById('result').style.display = 'none';
  document.getElementById('spinner').style.display = 'block';

  const formData = new FormData();
  formData.append('file', file);

  fetch('/parse', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(data => {
      document.getElementById('spinner').style.display = 'none';
      if (data.error) { showError(data.error); return; }
      document.getElementById('out-subject').textContent = data.subject || '（なし）';
      document.getElementById('out-from').textContent = data.sender || '（なし）';
      document.getElementById('out-to').textContent = data.to || '（なし）';
      document.getElementById('out-body').textContent = data.body || '（本文なし）';
      document.getElementById('result').style.display = 'block';
    })
    .catch(e => showError('サーバーエラー: ' + e.message));
}

function copyBody() {
  const text = document.getElementById('out-body').textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = '✅ コピーしました';
    setTimeout(() => btn.textContent = '📋 本文をコピー', 2000);
  });
}

function reset() {
  document.getElementById('result').style.display = 'none';
  document.getElementById('error').style.display = 'none';
  fileInput.value = '';
}
</script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML.encode('utf-8'))

    def do_POST(self):
        if self.path != '/parse':
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        result = self._parse_oft(content_type, body)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

    def _parse_oft(self, content_type, raw_body):
        import re
        boundary_match = re.search(r'boundary=([^\s;]+)', content_type)
        if not boundary_match:
            return {'error': 'マルチパートデータが見つかりません'}

        boundary = boundary_match.group(1).encode()
        parts = raw_body.split(b'--' + boundary)
        file_data = None
        for part in parts:
            if b'filename=' in part:
                header_end = part.find(b'\r\n\r\n')
                if header_end != -1:
                    file_data = part[header_end+4:].rstrip(b'\r\n')
                    break

        if not file_data:
            return {'error': 'ファイルデータが見つかりません'}

        try:
            import extract_msg
            with tempfile.NamedTemporaryFile(suffix='.oft', delete=False) as f:
                f.write(file_data)
                tmp_path = f.name

            try:
                msg = extract_msg.openMsg(tmp_path)
                subject = msg.subject or ''
                sender = msg.sender or ''
                to = msg.to or ''
                body = msg.body or ''
                if not body and hasattr(msg, 'htmlBody') and msg.htmlBody:
                    import re as re2
                    body = re2.sub(r'<[^>]+>', '', msg.htmlBody.decode('utf-8', errors='ignore'))
                msg.close()
            finally:
                os.unlink(tmp_path)

            return {
                'subject': subject.strip(),
                'sender': sender.strip(),
                'to': to.strip(),
                'body': body.strip()
            }
        except ImportError:
            return {'error': 'extract-msg がインストールされていません。\nターミナルで: pip3 install extract-msg'}
        except Exception as e:
            return {'error': f'解析エラー: {str(e)}'}


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    server = http.server.HTTPServer(('0.0.0.0', port), Handler)
    print(f'✅ OFT ビューワー起動中')
    print(f'👉 ブラウザで開く: http://localhost:{port}')
    print(f'   終了するには Ctrl+C')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n停止しました')
