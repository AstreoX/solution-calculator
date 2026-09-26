---
name: solution-calculator-release
description: 配液计算器（solution-calculator，uni-app x 安卓 App，仓库 AstreoX/solution-calculator）的版本更新与公告发布流程：调版本号、打包、生成 update.json、上传 GitHub Release、推送、发布后核对，以及发 / 改 / 撤公告、强制更新、撤回有问题的版本、排查「用户收不到更新或公告」。只要用户在这个项目里提到发版、发布新版本、上传安装包 / APK、更新 update.json、Release、发公告、推送通知、公告栏、强制更新、回滚版本、用户没收到更新，或者想让已安装的 App 看到什么消息，就使用这个 skill，即使用户没有明确说「update.json」。
---

# 配液计算器：版本更新与公告发布

App 不连任何自建服务器。更新和公告全靠仓库根目录的一个 `update.json`（充当版本信息和公告栏），安装包放在 GitHub Releases。App 每次启动读取这个文件，发现新版本就弹出更新窗口、在 App 内下载安装；有公告就弹出或放进「设置 → 版本与公告」。

所以「发版」和「发公告」本质上都是**改 `update.json` 并推送到 `main` 分支**。发版还要先把安装包传到 Release。

## 关键位置

| 内容 | 位置 |
|---|---|
| 仓库 | `https://github.com/AstreoX/solution-calculator`，分支 `main`，本地 `E:\IDEProjects\Chemistry_caculator` |
| update.json | 仓库根目录 `update.json`（还没发过版时不存在，App 读不到就什么都不弹） |
| App 读取地址 | `CC-uni-app-x/common/config.uts` 的 `UPDATE_SOURCES`：GitHub raw，其次 jsDelivr 镜像（Gitee 位置留了注释） |
| 维护脚本 | `tools/release/make_update.py`（生成版本信息、增删公告），配置 `tools/release/release.config.json` |
| 核对脚本 | 本 skill 的 `scripts/check_release.py` |
| App 端实现 | `CC-uni-app-x/common/update.uts`、`components/update-sheet/`、`pages/settings/about.uvue` |
| 格式和 App 行为细节 | 本 skill 的 `references/update-json.md`（写复杂公告或排查问题时再读） |

## 动手前先确认

建 Release、推送都会把内容公开，而且已安装的 App 马上就能读到。所以执行这两步前，先把要发布的内容（版本号、更新说明、公告文字）给用户看，得到确认再动手。改本地文件、跑检查可以直接做。

另外有几条底线，任何一条不满足都先停下，和用户说明：
- **签名要一致**：安装包必须用和已发版本相同的证书打包（目前是 HBuilderX 的「云端证书」，包名 `uni.UNIF0DF08B`），否则用户无法覆盖安装。
- **版本号要变大**：`versionCode` 必须比 `update.json` 里现有的大，App 只比较这个数。
- **不提交机密**：`keystore/`、任何 API Key 都不能进仓库。`config.uts` 里不应出现 `sk-` 开头的字符串。

## 发布新版本

1. **调版本号**：改 `CC-uni-app-x/manifest.json` 里的 `versionName`（如 `1.0.1`）和 `versionCode`（如 `101`，通常是版本名去掉点）。提交这个改动。

2. **打包**：由用户在 HBuilderX 里点「发行 → 原生 App-云打包」，证书选「云端证书」，打好的 apk 一般在下载目录。
   - 这台电脑的 Clash 是全局模式时，命令行 `cli pack` 连不上 DCloud 服务器（`app.liuyingyong.cn` 的 TLS 握手会被断开），所以打包交给用户在界面里操作。
   - 拿到 apk 后先检查一遍，确认包名、版本号、签名都对：
     ```bash
     "E:/Program Files/HBuilderX/plugins/uts-development-android/static/win/aapt2.exe" dump badging <apk> | grep -E "^package|sdkVersion"
     "E:/Program Files/HBuilderX/plugins/amazon-corretto/bin/java.exe" -jar "E:/Program Files/HBuilderX/plugins/app-safe-pack/apksigner.jar" verify -v <apk>
     ```

3. **生成 update.json**：
   ```bash
   python tools/release/make_update.py release <apk路径> --notes "· 修复……\n· 新增……"
   ```
   - 脚本会从 apk 读出版本号，把安装包复制成 `tools/release/dist/chemcalc-<版本>.apk`，写好大小、sha1、下载地址和 Release 页面地址。原有公告保持不变。
   - 版本号没变大时脚本会拒绝，这时回到第 1 步，不要加 `--force` 绕过。
   - 更新说明写给普通用户看，每条一行、以「· 」开头，讲用户能感知到的变化。
   - 需要强制更新时加 `--min-version-code <号>`，详见下文。

4. **建 Release 并上传安装包**：标签 `v<版本>`（如 `v1.0.1`），附件是第 3 步生成的 `chemcalc-<版本>.apk`。**文件名不能改**，`update.json` 里的下载地址就是按这个名字拼的。
   - 本机装了 `gh` 且已登录：
     ```bash
     gh release create v1.0.1 tools/release/dist/chemcalc-1.0.1.apk --repo AstreoX/solution-calculator --title "v1.0.1" --notes "<更新说明>"
     ```
   - 没有 `gh`（目前这台电脑就没有）：请用户在网页上操作（Releases → Draft a new release），或者用户提供了 `GITHUB_TOKEN` 时调用 REST API 创建 Release 并上传附件。token 只从环境变量读，不写进任何文件。

5. **推送 update.json**：确认 Release 附件已经能下载后，再提交并推送。顺序不能反：先推 `update.json`，用户会拿到一个 404 的下载地址。
   ```bash
   git add update.json && git commit -m "发布 v1.0.1" && git push
   ```

6. **核对**（见下文「发布后核对」）。

## 公告

```bash
python tools/release/make_update.py notice --id 2026-10-01-maint --title "国庆期间识别服务维护" --body "10 月 1 日 22:00–23:00 扫描识别可能失败，可手动填写。" --level warn --popup --expires 2026-10-02
python tools/release/make_update.py notice --remove 2026-10-01-maint
python tools/release/make_update.py show
```

改完同样提交并推送 `update.json`。

写公告时的判断：
- **`--popup` 少用**：弹窗会打断操作，留给需要马上知道的事（服务故障、必须升级、数据相关提醒）。一般消息不加 `--popup`，用户会在齿轮的小圆点和「设置 → 版本与公告」里看到。
- **id 用「日期-简短英文」**，如 `2026-10-01-maint`，不能重复。
  - 用同一个 id 再运行一次，会修改内容，但已读过的用户不会再弹出。
  - 要让所有人重新看到，就换一个新 id。
- **临时性的事一定加 `--expires`**，过期后自动消失，避免公告栏堆满过时信息。
- **只针对部分版本的提醒用 `--min` / `--max`**，例如只提醒旧版用户升级：`--max 100`。
- **撤掉公告**用 `--remove`。已经弹给用户看过的撤不回来，只是之后不再显示。

## 强制更新

`--min-version-code N` 会让版本号低于 N 的用户看到**关不掉**的更新弹窗。只在旧版确实没法正常用时使用，例如接口变了、有严重错误。用之前先和用户确认。平时保持 0。

## 撤回有问题的版本

App 只在远端版本号大于本机时提示更新。
- **还没多少人更新**：把 `update.json` 的 `latest` 改回上一个版本的内容（`git log -p update.json` 能找到），推送。这样还没更新的人不会再收到提示。
- **已经更新的人**：他们不会自动回退。要发一个版本号更大的修复版，按正常流程发布。
- **不要删除 Release 附件**，除非 `update.json` 已经不再指向它，否则正在下载的用户会失败。

## 发布后核对

```bash
python skills/solution-calculator-release/scripts/check_release.py            # 格式 + 远端是否同步 + 下载地址可用
python skills/solution-calculator-release/scripts/check_release.py --full     # 另外把安装包完整下载下来核对 sha1
```

- **远端内容还是旧的**：GitHub raw 一般几分钟内更新。jsDelivr 缓存可能要几小时，可以访问 `https://purge.jsdelivr.net/gh/AstreoX/solution-calculator@main/update.json` 刷新。
- **下载地址 404**：多半是 Release 没建、标签不对，或者附件名和 `update.json` 不一致。
- **核对脚本走本机代理访问 GitHub**，结果只能说明「从这台电脑能访问」。国内用户直连 GitHub 可能很慢甚至打不开，这正是建议配 Gitee 镜像的原因（见下文）。

## 用户说收不到更新或公告时

按顺序排查：
1. **远端 `update.json` 已经是新内容吗？**跑核对脚本。
2. **用户装的包带更新功能吗？**2026-09-26 09:58 那个包是加这套功能之前打的，没有更新功能，只能手动装一次新包。
3. **版本号是不是真的变大了？**
4. **是不是选过「以后再说」？**同一版本当天不再弹。可以让用户去「设置 → 版本与公告 → 检查更新」。
5. **公告是不是过期了，或者被版本范围过滤掉了？**
6. **用户的网络能访问 GitHub raw 或 jsDelivr 吗？**不能的话，App 会一直用上次缓存的内容。
7. **下载完装不上？**多半是签名不一致（换过证书），或者手机没给「安装未知应用」权限。

## 配置 Gitee 镜像（可选，建议）

国内访问更稳。用户建好 Gitee 仓库后：
1. 把 `update.json` 同时推到 Gitee，并在 Gitee 建同名 Release、上传同一个 apk。
2. `release.config.json` 填上 `gitee`，`make_update.py` 会把 Gitee 下载地址排在最前。
3. `config.uts` 的 `UPDATE_SOURCES` 把 Gitee raw 地址放第一位，重新打包发一版，之后的用户才会走 Gitee。

Gitee 公开仓库需要审核；未登录下载附件有时会返回登录页。App 会校验大小和 sha1，识别出来后自动换 GitHub 下载，最后兜底用浏览器打开 Release 页面。
