# 第三方组件与数据声明

本项目自身的代码以 [MIT 许可证](LICENSE) 发布。项目中包含或使用了以下第三方内容，它们各自沿用原来的许可。

## 字体

安装包内置两款字体的子集。为了在安卓上与设计稿对齐，做了以下修改：
- 只保留用到的字符；
- 每个字重单独成一个字体族；
- 字体族改名为 `ns4` / `ns5` / `ns7`、`px4` / `px5` / `px6`；
- IBM Plex Serif 的 hhea 行高按其 Windows 指标重设。

按 SIL OFL 1.1 的要求，修改后的字体不再使用原字体名（包括 IBM Plex 的保留字体名「Plex」），并保留原版权与许可信息。

| 字体 | 版权 | 许可 | 文件 |
|---|---|---|---|
| Noto Serif SC（思源宋体） | © Google Inc.、Adobe | [SIL OFL 1.1](CC-uni-app-x/static/fonts/OFL-NotoSerifSC.txt) | `CC-uni-app-x/static/fonts/ns*.ttf` |
| IBM Plex Serif | © IBM Corp.，保留字体名「Plex」 | [SIL OFL 1.1](CC-uni-app-x/static/fonts/OFL-IBMPlexSerif.txt) | `CC-uni-app-x/static/fonts/px*.ttf` |

子集由 `tools/fonts/build_fonts.py` 从 [google/fonts](https://github.com/google/fonts) 的源文件生成。

## 图标

齿轮图标（`gear`）的路径取自 [Lucide](https://lucide.dev)，许可见 [ISC License](LICENSES/ISC-Lucide.txt)。其余图标来自本项目的界面设计稿，或按同一风格另行绘制。所有图标由 `tools/icons/build_icons.py` 生成。

## 化合物数据

离线化合物库（`CC-uni-app-x/static/db/`）由 `tools/db/` 下的脚本构建，来源详见 [tools/db/SOURCES.md](tools/db/SOURCES.md)：

| 数据 | 来源 | 许可 |
|---|---|---|
| 化学式、CAS 号、中英文名称与别名 | [Wikidata](https://www.wikidata.org)（经 QLever SPARQL 查询） | CC0 1.0 |
| 中文俗名 | 中文维基百科的条目标题与重定向标题（只用标题，不使用正文） | — |
| 原子量 | IUPAC / CIAAW 标准原子量（简化值） | 事实数据 |
| 常用试剂、「质量分数—密度」表 | 按国标与试剂目录人工整理，见 SOURCES.md | — |

App 运行时，离线库查不到的名称会联网查询 [PubChem](https://pubchem.ncbi.nlm.nih.gov)（英文名、CAS 号）和 Wikidata（中文名），查询结果缓存在用户本机。PubChem 数据的使用遵循 NCBI 的[数据政策](https://www.ncbi.nlm.nih.gov/home/about/policies/)。

## 运行时框架

App 基于 DCloud 的 [uni-app x](https://doc.dcloud.net.cn/uni-app-x/) 开发。打包出的安装包包含 uni-app x 运行时，其使用条款以 DCloud 官方说明为准。
