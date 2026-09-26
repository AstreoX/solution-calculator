# 版本更新与公告

App 每次启动时读取一个 `update.json`，用来提示新版本、下载安装包、弹出公告。这个文件和安装包都放在你自己的 Gitee（主）和 GitHub（备用）仓库里，不需要服务器。

当前配置：GitHub 仓库 [AstreoX/solution-calculator](https://github.com/AstreoX/solution-calculator)，`update.json` 放在仓库根目录（`main` 分支），安装包放在该仓库的 Releases。Gitee 镜像还没配置。

## 一次性配置

1. **建仓库**：在 Gitee 和 GitHub 各建一个公开仓库，比如都叫 `chemcalc`。
   - Gitee 的公开仓库要先通过审核，审核通过前，外部访问 raw 文件可能失败。
2. **填 App 里的读取地址**：打开 `CC-uni-app-x/common/config.uts`，在 `UPDATE_SOURCES` 里填上 raw 地址（分支名按实际填写）。App 会从上到下依次尝试，第一个成功的为准；全部失败时沿用上次缓存的内容：
   ```ts
   export const UPDATE_SOURCES : string[] = [
   	'https://gitee.com/<用户名>/chemcalc/raw/master/update.json',
   	'https://raw.githubusercontent.com/<用户名>/chemcalc/main/update.json',
   	'https://cdn.jsdelivr.net/gh/<用户名>/chemcalc@main/update.json'
   ]
   ```
   - 国内网络经常访问不了 `raw.githubusercontent.com`，所以加了第三个 jsDelivr 镜像。
   - jsDelivr 对分支内容有缓存，更新后可能要过几小时才生效。
3. **填发布脚本里的仓库**：第一次运行 `python tools/release/make_update.py show` 会生成 `tools/release/release.config.json`，在里面填上仓库名：
   ```json
   {"gitee": "<用户名>/chemcalc", "github": "<用户名>/chemcalc", "out": "tools/release/update.json"}
   ```
   `out` 可以直接写成你本地仓库目录里的 `update.json`，这样生成后直接提交即可。

改完 `UPDATE_SOURCES` 要重新打一次包。这一版的用户需要手动安装一次，从下一版开始就能在 App 内自动提示更新。

## 每次发新版本

1. **改版本号**：在 `manifest.json` 里调大 `versionName`（如 1.0.1）和 `versionCode`（如 101）。App 用 `versionCode` 判断有没有新版本。
2. **打包**：HBuilderX →「发行」→「原生 App-云打包」，证书继续用「云端证书」。签名必须和旧版一致，否则无法覆盖安装。
3. **生成 update.json**：
   ```bash
   python tools/release/make_update.py release <安装包路径> --notes "· 修复……\n· 新增……"
   ```
   - 版本号从安装包里读取。
   - 安装包会被复制成 `tools/release/dist/chemcalc-<版本>.apk`，同时写入大小、sha1 和两个下载地址。原有公告保持不变。
   - 加 `--min-version-code 101` 可以强制更新：低于这个版本号的用户无法关闭更新弹窗。
4. **建发行版**：Gitee 和 GitHub 各建一个发行版，标签为 `v<版本>`（如 `v1.0.1`），附件上传上一步生成的 `chemcalc-<版本>.apk`。**文件名不要改。**
5. **推送**：把 `update.json` 提交并推送到两个仓库。

**App 端的行为：**
- 下载时先试 Gitee，失败或拿到的不是安装包（例如要求登录时返回的网页）就换 GitHub。App 按大小和 sha1 校验，能识别出这种情况。
- 两个都下载失败时，会提示「改用浏览器下载」，打开发行版页面。
- 下载完成后调起系统安装程序。第一次安装时，系统会先要求允许「安装未知应用」。
- 选「以后再说」后，同一个版本当天不再弹出（强制更新除外）。

## 公告

```bash
python tools/release/make_update.py notice --id 2026-10-01-a --title "国庆期间识别服务维护" --body "10 月 1 日 22:00–23:00 可能无法识别，可手动填写。" --level warn --popup --expires 2026-10-02
python tools/release/make_update.py notice --remove 2026-10-01-a
python tools/release/make_update.py show
```

- `--popup`：启动时弹出，每条只弹一次。不加的话，只显示在「设置 → 版本与公告」里，首页齿轮上会出现小圆点提示。
- `--level warn`：显示为「重要公告」，标题用琥珀色。
- `--expires`：过期日期（含当天），过期后不再显示。
- `--min` / `--max`：只给某个版本号范围内的用户看，例如只提醒旧版用户升级。
- `id` 不能重复。改公告内容时用同一个 id 再运行一次即可覆盖；想让它重新弹出，就换一个新 id。

修改后同样要把 `update.json` 推送到两个仓库。

## update.json 格式

见 `update.example.json`。各字段说明：

**`latest`（最新版本）**

| 字段 | 说明 |
|---|---|
| `versionName` / `versionCode` | 版本名和版本号 |
| `minVersionCode` | 低于此版本号的必须更新 |
| `size` / `sha1` | 用于校验下载是否完整 |
| `notes` | 更新说明，`\n` 表示换行 |
| `urls` | 下载地址，按顺序尝试 |
| `page` | 浏览器兜底时打开的页面 |

**`notices`（公告列表）**

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识 |
| `title` / `body` / `date` | 标题、正文、日期 |
| `level` | `info` 或 `warn` |
| `popup` | 是否启动时弹出 |
| `minVersionCode` / `maxVersionCode` | 适用的版本号范围，`0` 表示不限 |
| `expires` | 过期日期 |
