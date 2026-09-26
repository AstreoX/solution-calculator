# 本地 skill

这里的 skill 是为这个项目写的操作手册，**特意没有放进 `.claude/skills/`，Claude Code 不会自动加载**。

- `solution-calculator-release/`：版本更新与公告发布（发版、上传 GitHub Release、生成 / 推送 update.json、发公告、强制更新、撤回版本、排查收不到更新）。

要用时有两种方式：
- 直接让 Claude 读取 `skills/solution-calculator-release/SKILL.md` 再照做；
- 想让它自动触发，就把整个目录复制到 `.claude/skills/`（项目级）或 `~/.claude/skills/`（个人级）。
