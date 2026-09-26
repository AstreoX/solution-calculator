"""维护 update.json：发布新版本、增删公告。

  python tools/release/make_update.py release <apk> --notes "· 修复……\n· 新增……" [--min-version-code 100]
  python tools/release/make_update.py notice --id 2026-09-27-a --title "标题" --body "正文" [--level warn] [--popup] [--expires 2026-10-31]
  python tools/release/make_update.py notice --remove 2026-09-27-a
  python tools/release/make_update.py show

仓库地址写在 tools/release/release.config.json（首次运行会生成模板）：
  {"gitee": "<用户名>/<仓库>", "github": "<用户名>/<仓库>", "out": "tools/release/update.json"}
"release" 会把安装包复制成 tools/release/dist/chemcalc-<版本>.apk（上传到两边 Release 的就是这个文件），
并写入大小、sha1、下载地址；原有公告保持不变。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(HERE, 'release.config.json')
AAPT2 = r'E:\Program Files\HBuilderX\plugins\uts-development-android\static\win\aapt2.exe'
MANIFEST = os.path.join(ROOT, 'CC-uni-app-x', 'manifest.json')


def load_config():
    if not os.path.exists(CONFIG):
        with open(CONFIG, 'w', encoding='utf-8') as f:
            json.dump({'gitee': '<用户名>/<仓库>', 'github': '<用户名>/<仓库>', 'out': 'tools/release/update.json'},
                      f, ensure_ascii=False, indent=2)
        print(f'已生成 {CONFIG}，请先填好 gitee / github 仓库再运行')
        sys.exit(1)
    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    if '<' in cfg.get('gitee', '<') and '<' in cfg.get('github', '<'):
        print(f'请先在 {CONFIG} 里填好仓库（用户名/仓库名）')
        sys.exit(1)
    return cfg


def out_path(cfg):
    p = cfg.get('out') or 'tools/release/update.json'
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_feed(path):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {'latest': None, 'notices': []}


def save_feed(path, feed):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'已写入 {path}')


def apk_version(apk):
    """版本号优先从安装包读（aapt2），读不到时退回 manifest.json。"""
    if os.path.exists(AAPT2):
        out = subprocess.run([AAPT2, 'dump', 'badging', apk], capture_output=True, text=True, encoding='utf-8').stdout
        m = re.search(r"versionCode='(\d+)' versionName='([^']+)'", out)
        if m:
            return m.group(2), int(m.group(1))
    with open(MANIFEST, encoding='utf-8') as f:
        txt = re.sub(r'/\*.*?\*/', '', f.read(), flags=re.S)
    m = json.loads(txt)
    print('（未能从安装包读取版本号，改用 manifest.json）')
    return m['versionName'], int(m['versionCode'])


def cmd_release(args):
    cfg = load_config()
    vn, vc = apk_version(args.apk)
    name = f'chemcalc-{vn}.apk'
    dist = os.path.join(HERE, 'dist')
    os.makedirs(dist, exist_ok=True)
    dst = os.path.join(dist, name)
    shutil.copyfile(args.apk, dst)
    data = open(dst, 'rb').read()
    tag = f'v{vn}'
    urls, page = [], ''
    if '<' not in cfg.get('gitee', '<'):
        urls.append(f"https://gitee.com/{cfg['gitee']}/releases/download/{tag}/{name}")
        page = f"https://gitee.com/{cfg['gitee']}/releases/tag/{tag}"
    if '<' not in cfg.get('github', '<'):
        urls.append(f"https://github.com/{cfg['github']}/releases/download/{tag}/{name}")
        page = page or f"https://github.com/{cfg['github']}/releases/tag/{tag}"
    path = out_path(cfg)
    feed = load_feed(path)
    old = feed.get('latest') or {}
    if old.get('versionCode', 0) >= vc and not args.force:
        print(f"update.json 里已是 {old.get('versionName')}（{old.get('versionCode')}），新包版本号 {vc} 没有变大。"
              f"请先在 manifest.json 里调大 versionName / versionCode 重新打包（或加 --force）")
        sys.exit(1)
    feed['latest'] = {
        'versionName': vn,
        'versionCode': vc,
        'minVersionCode': args.min_version_code,
        'date': args.date or datetime.date.today().isoformat(),
        'size': len(data),
        'sha1': hashlib.sha1(data).hexdigest(),
        'notes': args.notes.replace('\\n', '\n'),
        'urls': urls,
        'page': page,
    }
    feed.setdefault('notices', [])
    save_feed(path, feed)
    print(f'\n安装包：{dst}（{len(data) / 1048576:.1f} MB）')
    print('接下来：')
    print(f'  1. Gitee 和 GitHub 各建一个发行版，标签 {tag}，附件上传上面这个 {name}（文件名不要改）')
    print(f'  2. 把 {os.path.basename(path)} 提交并推送到两个仓库（和 App 里 UPDATE_SOURCES 指向的路径一致）')


def cmd_notice(args):
    cfg = load_config()
    path = out_path(cfg)
    feed = load_feed(path)
    notices = feed.setdefault('notices', [])
    if args.remove:
        before = len(notices)
        feed['notices'] = [n for n in notices if n.get('id') != args.remove]
        print('已删除' if len(feed['notices']) < before else f'没有找到公告 {args.remove}')
    else:
        if not args.id or not args.title:
            print('需要 --id 和 --title')
            sys.exit(1)
        n = {
            'id': args.id,
            'title': args.title,
            'body': (args.body or '').replace('\\n', '\n'),
            'date': args.date or datetime.date.today().isoformat(),
            'level': args.level,
            'popup': args.popup,
            'minVersionCode': args.min,
            'maxVersionCode': args.max,
            'expires': args.expires or '',
        }
        feed['notices'] = [x for x in notices if x.get('id') != args.id]
        feed['notices'].insert(0, n)  # 新公告放最前
        print(f"已{'更新' if len(feed['notices']) == len(notices) else '添加'}公告 {args.id}")
    save_feed(path, feed)


def cmd_show(args):
    cfg = load_config()
    print(json.dumps(load_feed(out_path(cfg)), ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description='维护 update.json（版本更新与公告）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('release', help='发布新版本')
    r.add_argument('apk')
    r.add_argument('--notes', required=True, help='更新说明，换行写 \\n')
    r.add_argument('--min-version-code', type=int, default=0, help='低于这个版本号的必须更新')
    r.add_argument('--date')
    r.add_argument('--force', action='store_true', help='版本号没变大也写入')
    r.set_defaults(fn=cmd_release)
    n = sub.add_parser('notice', help='添加 / 更新 / 删除公告')
    n.add_argument('--id')
    n.add_argument('--title')
    n.add_argument('--body')
    n.add_argument('--date')
    n.add_argument('--level', choices=['info', 'warn'], default='info')
    n.add_argument('--popup', action='store_true', help='启动时弹出（每条只弹一次）')
    n.add_argument('--min', type=int, default=0, help='只给不低于这个版本号的用户看')
    n.add_argument('--max', type=int, default=0, help='只给不高于这个版本号的用户看，0 为不限')
    n.add_argument('--expires', help='过期日期 YYYY-MM-DD（含当天）')
    n.add_argument('--remove', metavar='ID')
    n.set_defaults(fn=cmd_notice)
    s = sub.add_parser('show', help='查看当前 update.json')
    s.set_defaults(fn=cmd_show)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
