# update.json 格式与 App 端行为

App 端实现在 `CC-uni-app-x/common/update.uts`。改这里的规则时，同步更新本文件。

## 完整示例

```json
{
  "latest": {
    "versionName": "1.0.1",
    "versionCode": 101,
    "minVersionCode": 0,
    "date": "2026-10-01",
    "size": 27425022,
    "sha1": "25602484f170be5bdf16d476119e9f40ff9dea32",
    "notes": "· 扫描线覆盖整个取景框\n· 新增版本更新与公告栏",
    "urls": [
      "https://github.com/AstreoX/solution-calculator/releases/download/v1.0.1/chemcalc-1.0.1.apk"
    ],
    "page": "https://github.com/AstreoX/solution-calculator/releases/tag/v1.0.1"
  },
  "notices": [
    {
      "id": "2026-10-01-maint",
      "title": "国庆期间识别服务维护",
      "body": "10 月 1 日 22:00–23:00 扫描识别可能失败，可手动填写。",
      "date": "2026-10-01",
      "level": "warn",
      "popup": true,
      "minVersionCode": 0,
      "maxVersionCode": 0,
      "expires": "2026-10-02"
    }
  ]
}
```

`latest` 和 `notices` 都可以缺省。只要有其中一个，App 就认为这是合法内容。

## latest 字段

| 字段 | 说明 | App 怎么用 |
|---|---|---|
| `versionName` | 显示用的版本名 | 弹窗标题下的版本号 |
| `versionCode` | 整数，必须递增 | 大于本机版本号（`uni.getAppBaseInfo().appVersionCode`）才算有新版本；0 或缺省时整个 `latest` 被忽略 |
| `minVersionCode` | 强制更新线，0 表示不强制 | 本机版本号小于它时，弹窗没有「以后再说」，点遮罩、按返回键都关不掉 |
| `date` | 发布日期 | 显示在弹窗里 |
| `size` | 字节数 | 下载后核对大小，不一致就换下一个地址；为 0 时只要求文件大于 1 MB |
| `sha1` | 小写十六进制 | 非空时下载后核对 |
| `notes` | 更新说明，`\n` 表示换行 | 显示在弹窗的灰色框里 |
| `urls` | 下载地址数组，按顺序尝试 | 一个失败（网络错误、非 200、大小或 sha1 不符）就换下一个 |
| `page` | Release 页面 | 所有地址都失败时，「改用浏览器下载」打开它 |

## notices 每一项

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识；已读记录按 id 保存，本机最多保留最近 200 个 |
| `title` | 必填；`id` 或 `title` 为空的公告会被忽略 |
| `body` | 正文，`\n` 表示换行 |
| `date` | 显示用 |
| `level` | `info`（默认）或 `warn`。`warn` 显示为「重要公告」，标题和图标用琥珀色 |
| `popup` | `true` 时启动弹出，每条只弹一次（点「知道了」即记为已读） |
| `minVersionCode` / `maxVersionCode` | 只对这个版本号范围内的用户显示，0 表示不限 |
| `expires` | `YYYY-MM-DD`，含当天；过期后不显示 |

公告按数组顺序显示，`make_update.py notice` 会把新公告插在最前。

## App 启动时的完整流程

1. 首页显示约 1.2 秒后开始检查（`UPDATE_SOURCES` 为空时直接跳过）。
2. 先用本机缓存的上一份内容刷新公告和小圆点，所以离线也能看到。
3. 按 `UPDATE_SOURCES` 的顺序请求，每个超时 6 秒，地址后面带一个按分钟变化的参数 `?t=` 来绕过缓存。第一个返回合法内容的为准，并写入缓存。
4. 有新版本，并且（是强制更新，或者今天没选过「以后再说」）时，弹出更新窗口。
5. 没有要弹的更新时，按顺序弹出未读的 `popup` 公告，一次一条，点「知道了」再弹下一条。
6. 选「以后再说」后，记录「版本号@日期」，同一版本当天不再弹；之后接着弹未读公告。

## 下载与安装

- 保存到 `USER_DATA_PATH/chemcalc-<versionCode>.apk`。如果这个文件已经存在且校验通过（比如上次装到一半取消了），直接调起安装，不重新下载。
- 下载超时 10 分钟，进度条显示已下载 MB 和百分比。
- 校验通过后调用 `uni.installApk`。第一次安装时，系统会要求允许「安装未知应用」，这是安卓的正常流程。
- `manifest.json` 里需要 `REQUEST_INSTALL_PACKAGES` 权限（已加）。

## 入口与提示

- 首页齿轮右上角的小圆点：有新版本或有未读公告时显示。
- 「设置 → 版本与公告」：
  - 显示当前版本，提供「检查更新 / 更新」按钮；
  - 列出公告，进入时未读的公告标蓝点；
  - 离开这个页面时，所有公告记为已读。

## 本机存储的键（排查用）

| 键 | 内容 |
|---|---|
| `update-feed` | 上次拿到的 update.json |
| `notice-read` | 已读公告 id 列表 |
| `update-later` | 「以后再说」的记录，格式 `versionCode@YYYY-MM-DD` |
