"""Generate the app's SVG icons (one file per icon/color/stroke) from the design's exact paths.

Output: CC-uni-app-x/static/icons/<name>-<hex>.svg
Run: python tools/icons/build_icons.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'CC-uni-app-x', 'static', 'icons')

# name -> (viewBox, stroke-width or None for filled, inner svg)
ICONS = {
    'scan': ('0 0 24 24', 1.75, '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8"/><path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8"/>'
             '<path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M7.5 12h9"/>'),
    'check': ('0 0 24 24', 1.75, '<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
    'checkb': ('0 0 24 24', 1.9, '<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
    'warn': ('0 0 24 24', 1.75, '<path d="M12 4 2.5 20h19L12 4z"/><path d="M12 10v4.5M12 17.2v.3"/>'),
    'flask': ('0 0 24 24', 1.75, '<path d="M9 3h6"/><path d="M10 3v6.5L4.8 18.2A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-2.8L14 9.5V3"/><path d="M7.2 15h9.6"/>'),
    'drop': ('0 0 24 24', 1.75, '<path d="M12 3.5c3 3.6 6 7 6 10.5a6 6 0 0 1-12 0c0-3.5 3-6.9 6-10.5z"/><path d="M9 15a3 3 0 0 0 3 3"/>'),
    'layers': ('0 0 24 24', 1.75, '<path d="M12 3 3 7.5l9 4.5 9-4.5L12 3z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>'),
    'chev': ('0 0 24 24', 2.2, '<path d="m6 9 6 6 6-6"/>'),
    'chevs': ('0 0 24 24', 2.4, '<path d="m6 9 6 6 6-6"/>'),
    'close': ('0 0 24 24', 1.75, '<path d="M6 6l12 12M18 6 6 18"/>'),
    'plus': ('0 0 24 24', 1.75, '<path d="M12 5v14M5 12h14"/>'),
    'info': ('0 0 24 24', 1.8, '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.5v.3"/>'),
    'gallery': ('0 0 24 24', 1.75, '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m20.5 16-5-5L6 19.5"/>'),
    'lock': ('0 0 24 24', 2.0, '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>'),
    'tri': ('0 0 10 10', None, '<path d="M5 .8 9.6 9.2H.4z"/>'),
    # 设置齿轮 / 返回（设计稿之外新增，沿用同样的 24 视框、1.75 描边、圆角端点）
    'gear': ('0 0 24 24', 1.75, '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>'),
    'back': ('0 0 24 24', 2.0, '<path d="m15 18-6-6 6-6"/>'),
    # 版本更新 / 公告
    'download': ('0 0 24 24', 1.9, '<path d="M12 4v11"/><path d="m7 10.5 5 5 5-5"/><path d="M4.5 16.5v2A1.5 1.5 0 0 0 6 20h12a1.5 1.5 0 0 0 1.5-1.5v-2"/>'),
    # 设置菜单
    'spark': ('0 0 24 24', 1.75, '<path d="M11 4.5 12.7 9.3a1 1 0 0 0 .6.6L18 11.5l-4.7 1.6a1 1 0 0 0-.6.6L11 18.5l-1.7-4.8a1 1 0 0 0-.6-.6L4 11.5l4.7-1.6a1 1 0 0 0 .6-.6z"/><path d="M18.5 3v3.5M16.75 4.75h3.5"/>'),
    'book': ('0 0 24 24', 1.75, '<path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v13H6.5A1.5 1.5 0 0 0 5 18.5z"/><path d="M5 18.5A1.5 1.5 0 0 0 6.5 20H19v-3"/><path d="M9 8.5h6"/>'),
    'trash': ('0 0 24 24', 1.75, '<path d="M4.5 7h15"/><path d="M9.5 7V4.5h5V7"/><path d="m6.5 7 .9 11.6A1.5 1.5 0 0 0 8.9 20h6.2a1.5 1.5 0 0 0 1.5-1.4L17.5 7"/><path d="M10.5 11v5M13.5 11v5"/>'),
    'chevr': ('0 0 24 24', 2.0, '<path d="m9 6 6 6-6 6"/>'),
    'bell': ('0 0 24 24', 1.75, '<path d="M6 10a6 6 0 0 1 12 0c0 4.5 1.8 6.2 2.5 7H3.5c.7-.8 2.5-2.5 2.5-7z"/><path d="M10 20.2a2.2 2.2 0 0 0 4 0"/>'),
}

# (name, color) pairs actually used by the UI
USES = [
    ('scan', '1F5FAD'), ('check', '1F5FAD'), ('checkb', 'FFFFFF'), ('warn', 'F2B35A'),
    ('flask', '1F5FAD'), ('flask', '4F555A'), ('drop', '1F5FAD'), ('drop', '4F555A'),
    ('layers', '1F5FAD'), ('layers', '4F555A'),
    ('chev', '4F555A'), ('chevs', '4F555A'),
    ('close', '62686C'), ('close', 'F3F4F1'), ('plus', '1F5FAD'), ('info', 'AEB4B8'),
    ('gallery', 'F3F4F1'), ('lock', 'FFFFFF'),
    ('tri', 'A3261B'), ('tri', '8A4B00'), ('tri', '1F5FAD'),
    ('tri', 'FF8A7A'), ('tri', 'F2B35A'), ('tri', '8CB8F2'),
    ('gear', '4F555A'), ('back', '16191B'), ('check', '2E7D32'), ('warn', '8A4B00'),
    ('download', 'FFFFFF'), ('bell', '1F5FAD'), ('bell', '8A4B00'),
    ('spark', '1F5FAD'), ('chevr', '8C959C'),
    ('book', '4F555A'), ('book', '1F5FAD'), ('trash', '62686C'),
]


def svg(name, color):
    vb, sw, inner = ICONS[name]
    w = vb.split()[2]
    if sw is None:
        style = f'fill="#{color}" stroke="none"'
    else:
        style = (f'fill="none" stroke="#{color}" stroke-width="{sw}" '
                 f'stroke-linecap="round" stroke-linejoin="round"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{w}">'
            f'<g {style}>{inner}</g></svg>\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, color in USES:
        with open(os.path.join(OUT, f'{name}-{color}.svg'), 'w', encoding='utf-8') as f:
            f.write(svg(name, color))
    print(f'{len(USES)} icons -> {OUT}')


if __name__ == '__main__':
    main()
