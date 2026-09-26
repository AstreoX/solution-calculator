"""自建 OCR 服务（App 里 OCR.provider = 'custom' 时使用）

协议：POST <url>  JSON {"image": "<base64 JPEG/PNG>"}
     → {"lines": [{"text": "...", "box": [x, y, w, h]}, ...]}   （坐标为原图像素）
可选鉴权：启动时传 --token，App 的 OCR.customToken 填同一个值（请求头 Authorization: Bearer <token>）

依赖：pip install rapidocr onnxruntime   （首次运行会自动下载中英文识别模型）
运行：python ocr_server.py --port 8866 [--token xxx]
"""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from rapidocr import RapidOCR

engine = RapidOCR()
TOKEN = ''


def recognize(img_bytes: bytes) -> list:
    res = engine(img_bytes)
    lines = []
    boxes = getattr(res, 'boxes', None)
    txts = getattr(res, 'txts', None)
    if boxes is None or txts is None:
        return lines
    for box, text in zip(boxes, txts):
        pts = np.array(box, dtype=float)
        x0, y0 = pts[:, 0].min(), pts[:, 1].min()
        x1, y1 = pts[:, 0].max(), pts[:, 1].max()
        lines.append({'text': str(text), 'box': [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]})
    # 按行排序：先上后下，同一行从左到右
    lines.sort(key=lambda l: (round(l['box'][1] / max(8.0, l['box'][3] * 0.6)), l['box'][0]))
    return lines


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if TOKEN and self.headers.get('Authorization', '') != 'Bearer ' + TOKEN:
            self._send(401, {'error': 'unauthorized'})
            return
        try:
            if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                raw = b''
                while True:
                    size = int(self.rfile.readline().strip() or b'0', 16)
                    if size == 0:
                        self.rfile.readline()
                        break
                    raw += self.rfile.read(size)
                    self.rfile.readline()
            else:
                n = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(n)
            data = json.loads(raw.decode('utf-8'))
            img = base64.b64decode(data['image'])
            self._send(200, {'lines': recognize(img)})
        except Exception as e:  # noqa: BLE001
            self._send(400, {'error': str(e)})

    def log_message(self, fmt, *args):
        print('[ocr]', fmt % args, flush=True)


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8866)
    ap.add_argument('--token', default='')
    a = ap.parse_args()
    TOKEN = a.token
    print(f'OCR server on http://{a.host}:{a.port}')
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
