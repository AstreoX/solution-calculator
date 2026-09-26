"""核对配液计算器的 update.json：格式、与 manifest 版本号是否对得上、远端是否已同步、下载地址是否可用。

  python skills/solution-calculator-release/scripts/check_release.py            # 常规检查
  python skills/solution-calculator-release/scripts/check_release.py --full     # 另外完整下载安装包核对 sha1
  python skills/solution-calculator-release/scripts/check_release.py --file tools/release/update.example.json --no-remote

读取地址默认取自 CC-uni-app-x/common/config.uts 里未注释的 UPDATE_SOURCES。
网络请求走系统代理环境变量（HTTPS_PROXY 等），结果只代表「从这台电脑能访问」。
退出码：0 没有问题，1 有需要处理的问题。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
APP = os.path.join(ROOT, 'CC-uni-app-x')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

problems = 0


def ok(msg):
    print('  ✓ ' + msg)


def warn(msg):
    print('  ! ' + msg)


def bad(msg):
    global problems
    problems += 1
    print('  ✗ ' + msg)


def fetch(url, timeout=20, limit=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'solution-calculator-release-check'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit) if limit else r.read()
        return r.status, r.headers, data


def manifest_version():
    try:
        txt = open(os.path.join(APP, 'manifest.json'), encoding='utf-8').read()
        m = json.loads(re.sub(r'/\*.*?\*/', '', txt, flags=re.S))
        return m.get('versionName'), int(m.get('versionCode'))
    except Exception:
        return None, None


def sources_from_config():
    try:
        txt = open(os.path.join(APP, 'common', 'config.uts'), encoding='utf-8').read()
    except OSError:
        return []
    m = re.search(r'UPDATE_SOURCES\s*:\s*string\[\]\s*=\s*\[(.*?)\]', txt, flags=re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith('//'):
            continue
        q = re.search(r"'([^']+)'", s)
        if q:
            out.append(q.group(1))
    return out


def check_format(feed):
    print('格式')
    today = datetime.date.today().isoformat()
    rel = feed.get('latest')
    if rel is None:
        warn('没有 latest（只发公告，不提示更新）')
    else:
        vc = rel.get('versionCode')
        if not isinstance(vc, int) or vc <= 0:
            bad('latest.versionCode 必须是正整数，现在是 %r' % (vc,))
        else:
            ok('最新版本 %s（%d）' % (rel.get('versionName'), vc))
        mv = rel.get('minVersionCode', 0)
        if isinstance(mv, int) and mv > 0:
            warn('设置了强制更新：版本号低于 %d 的用户无法关闭更新弹窗' % mv)
        if not isinstance(rel.get('size'), int) or rel.get('size', 0) <= 0:
            warn('没有 size，App 只能粗略判断下载是否完整')
        sha1 = rel.get('sha1', '')
        if sha1 and not re.fullmatch(r'[0-9a-f]{40}', sha1):
            bad('sha1 格式不对（应为 40 位小写十六进制）')
        urls = rel.get('urls') or []
        if not urls and not rel.get('page'):
            bad('urls 和 page 都为空，用户没有地方下载')
        for u in urls:
            if '<' in u or not u.startswith('https://'):
                bad('下载地址不像真实地址：%s' % u)
        if rel.get('date') and not DATE.match(rel['date']):
            warn('date 不是 YYYY-MM-DD：%s' % rel['date'])
    notices = feed.get('notices') or []
    ids = set()
    active = 0
    for n in notices:
        nid = n.get('id', '')
        if not nid or not n.get('title'):
            bad('有公告缺少 id 或 title（App 会忽略它）：%r' % (nid or n.get('title')))
            continue
        if nid in ids:
            bad('公告 id 重复：%s' % nid)
        ids.add(nid)
        if n.get('level', 'info') not in ('info', 'warn'):
            warn('公告 %s 的 level 不是 info / warn' % nid)
        exp = n.get('expires', '')
        if exp and not DATE.match(exp):
            bad('公告 %s 的 expires 不是 YYYY-MM-DD：%s' % (nid, exp))
        elif exp and exp < today:
            warn('公告 %s 已于 %s 过期，App 不再显示，可以删除' % (nid, exp))
        else:
            active += 1
    ok('公告 %d 条（当前有效 %d 条，其中启动弹出 %d 条）' % (
        len(notices), active, sum(1 for n in notices if n.get('popup') and not (n.get('expires') and n['expires'] < today))))


def check_manifest(feed):
    print('与 manifest.json 对照')
    name, code = manifest_version()
    rel = feed.get('latest') or {}
    if code is None:
        warn('读不到 manifest.json 的版本号')
        return
    vc = rel.get('versionCode')
    if not isinstance(vc, int):
        return
    if vc == code:
        ok('manifest 版本 %s（%d）与 update.json 一致' % (name, code))
    elif code > vc:
        warn('manifest 已经是 %s（%d），比 update.json 的 %d 新：新版还没发布？' % (name, code, vc))
    else:
        warn('update.json 的 %d 比 manifest 的 %d 还新：manifest 的改动没提交？' % (vc, code))


def check_remote(feed, sources, expect_missing=False):
    print('远端 update.json')
    if not sources:
        warn('UPDATE_SOURCES 为空，App 不会检查更新')
        return
    for i, u in enumerate(sources):
        url = u + ('&' if '?' in u else '?') + 't=%d' % int(time.time())
        try:
            st, _, data = fetch(url, timeout=15)
            remote = json.loads(data.decode('utf-8'))
            if remote == feed:
                ok('%d. 已同步：%s' % (i + 1, u))
            else:
                rv = (remote.get('latest') or {}).get('versionCode')
                warn('%d. 内容与本地不同（远端版本号 %s），可能是还没推送或缓存未刷新：%s' % (i + 1, rv, u))
        except urllib.error.HTTPError as e:
            if expect_missing and e.code == 404:
                ok('%d. 远端也还没有（还没发过版，正常）：%s' % (i + 1, u))
            else:
                (bad if i == 0 else warn)('%d. HTTP %d：%s' % (i + 1, e.code, u))
        except Exception as e:
            (bad if i == 0 else warn)('%d. 无法访问（%s）：%s' % (i + 1, type(e).__name__, u))
    if any('jsdelivr' in u for u in sources):
        print('    jsDelivr 缓存刷新：https://purge.jsdelivr.net/gh/AstreoX/solution-calculator@main/update.json')


def check_downloads(feed, full):
    print('安装包下载地址')
    rel = feed.get('latest') or {}
    urls = rel.get('urls') or []
    if not urls:
        warn('没有下载地址')
        return
    size, sha1 = rel.get('size', 0), rel.get('sha1', '')
    good = 0
    for i, u in enumerate(urls):
        if '<' in u:
            warn('%d. 跳过占位地址：%s' % (i + 1, u))
            continue
        try:
            if full:
                st, hd, data = fetch(u, timeout=300)
                h = hashlib.sha1(data).hexdigest()
                if size and len(data) != size:
                    bad('%d. 大小 %d 与 update.json 的 %d 不符：%s' % (i + 1, len(data), size, u))
                elif sha1 and h != sha1:
                    bad('%d. sha1 不符：%s' % (i + 1, u))
                else:
                    good += 1
                    ok('%d. 可下载，大小和 sha1 一致（%.1f MB）：%s' % (i + 1, len(data) / 1048576, u))
            else:
                st, hd, data = fetch(u, timeout=60, limit=4)
                ctype = hd.get('Content-Type', '')
                clen = int(hd.get('Content-Length') or 0)
                if 'text/html' in ctype or data[:2] != b'PK':
                    bad('%d. 返回的不是安装包（%s），可能要求登录或地址错了：%s' % (i + 1, ctype, u))
                elif size and clen and clen != size:
                    bad('%d. 文件大小 %d 与 update.json 的 %d 不符：%s' % (i + 1, clen, size, u))
                else:
                    good += 1
                    ok('%d. 可下载（%s）：%s' % (i + 1, ('%.1f MB' % (clen / 1048576)) if clen else '大小未知', u))
        except urllib.error.HTTPError as e:
            bad('%d. HTTP %d（Release 没建、标签不对或附件名不一致？）：%s' % (i + 1, e.code, u))
        except Exception as e:
            bad('%d. 无法下载（%s）：%s' % (i + 1, type(e).__name__, u))
    if good == 0 and urls:
        print('    所有地址都不可用时，App 只能提示用户用浏览器打开：%s' % rel.get('page', '（没有 page）'))


def main():
    ap = argparse.ArgumentParser(description='核对 update.json')
    ap.add_argument('--file', default=os.path.join(ROOT, 'update.json'))
    ap.add_argument('--full', action='store_true', help='完整下载安装包核对 sha1')
    ap.add_argument('--no-remote', action='store_true', help='只检查本地文件，不联网')
    args = ap.parse_args()
    path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
    sources = sources_from_config()
    print('update.json：%s' % path)
    if not os.path.exists(path):
        print('  ! 本地还没有 update.json（还没发过版）。发版时用 tools/release/make_update.py release 生成。')
        if not args.no_remote:
            check_remote({}, sources, expect_missing=True)
        return 0 if problems == 0 else 1
    try:
        feed = json.load(open(path, encoding='utf-8'))
    except ValueError as e:
        print('  ✗ 不是合法的 JSON：%s' % e)
        return 1
    check_format(feed)
    check_manifest(feed)
    if not args.no_remote:
        check_remote(feed, sources)
        check_downloads(feed, args.full)
    print('\n%s' % ('没有发现问题' if problems == 0 else '有 %d 个问题需要处理' % problems))
    return 0 if problems == 0 else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
