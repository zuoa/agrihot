# AgriHot Skill 安装

用自然语言检索农业政策、资讯、论文、已收录全文和农业农村日报。

## 准备

在 https://agrihot.com/agent#apply 填写读取 Key 申请。管理员审批后人工交付 Key。

## 配置读取 Key

推荐在运行 Agent 的用户主目录下创建 `.agrihot` 目录，并用文本编辑器将读取 Key 保存到其中的 `.env` 文件，以 UTF-8 编码保存：

```dotenv
AGRIHOT_API_KEY=替换为你的读取Key
```

| 系统 | 配置文件位置 |
| --- | --- |
| macOS / Linux | `~/.agrihot/.env` |
| Windows | `%USERPROFILE%\.agrihot\.env`，例如 `C:\Users\你的用户名\.agrihot\.env` |

这里的 `~` 和 `%USERPROFILE%` 表示当前用户主目录，不是文件夹的字面名称。Windows 请确认文件名为 `.env`，不是 `.env.txt`；PowerShell 中可用 `$HOME\.agrihot\.env` 表示此路径。

Skill 会在执行请求时直接读取此文件，无需给 Agent 单独配置环境变量或修改 Shell 启动文件。若 Agent 执行环境已有非空的 `AGRIHOT_API_KEY` 环境变量，则优先使用它；为空或未设置时才读取文件。文件更新后，下一次请求即可读取新配置。

配置支持空行、整行 `#` 注释和成对的单引号或双引号；Key 值按原样读取，不执行命令、不展开变量，也不解析行尾注释。已有文件只需新增或更新 `AGRIHOT_API_KEY`，保留其他配置。不要将 Key 写进 Skill 文件、安装提示词或提交到仓库；macOS / Linux 可用 `chmod 600 ~/.agrihot/.env` 限制文件读取权限。

如果 Agent 在 WSL、容器或远程主机中执行，请将文件放在该执行环境的用户主目录下，并确保 Agent 有权读取。此文件用于 Skill，MCP 客户端仍按下文配置认证头。

## 安装

下载 https://agrihot.com/agrihot-skill/SKILL.md ，以 UTF-8 保存为 `agrihot/SKILL.md`。

- 通用 Agent Skills：`~/.agents/skills/agrihot/SKILL.md`
- Codex：使用当前环境支持的 skills 目录；若已有通用目录支持，优先复用。
- Claude Code：`~/.claude/skills/agrihot/SKILL.md`

只安装这个 Skill。若目标目录已存在，先检查内容；相同则无需修改，不同则保留原文件并由用户确定是否更新。不要覆盖其他 Skill 或修改全局 Agent 配置。

这是一个独立的 SKILL.md，不需要额外依赖。安装后多数 Agent 需要开启新会话才能发现新 Skill。

## 验证

新会话中询问：“过去一周，农业遥感领域有哪些值得关注的进展？”

成功时，回答会说明时间范围、给出中文摘要并引用 AgriHot 阅读链接。未配置 Key 时应提示配置 `.agrihot/.env` 或环境变量，没有 Key 时再引导申请；验证只报告配置状态，不输出 Key。检索降级时应明确说明，不能宣称已完成完整语义召回。

使用说明：https://agrihot.com/api/v1/agent
MCP：https://agrihot.com/api/v1/mcp （Streamable HTTP，认证头为 `Authorization: Bearer <读取Key>`）
