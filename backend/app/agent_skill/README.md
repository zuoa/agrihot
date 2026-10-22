# AgriHot Skill 安装

用自然语言检索农业政策、资讯、论文、已收录全文和农业农村日报。

## 准备

在 https://agrihot.com/agent#apply 填写读取 Key 申请。管理员审批后人工交付 Key。
将 Key 配置为 Agent 执行环境的 `AGRIHOT_API_KEY`，不要写进 Skill 文件或提交到仓库。

## 安装

下载 https://agrihot.com/agrihot-skill/SKILL.md ，以 UTF-8 保存为 `agrihot/SKILL.md`。

- 通用 Agent Skills：`~/.agents/skills/agrihot/SKILL.md`
- Codex：使用当前环境支持的 skills 目录；若已有通用目录支持，优先复用。
- Claude Code：`~/.claude/skills/agrihot/SKILL.md`

只安装这个 Skill。若目标目录已存在，先检查内容；相同则无需修改，不同则保留原文件并由用户确定是否更新。不要覆盖其他 Skill 或修改全局 Agent 配置。

这是一个独立的 SKILL.md，不需要额外依赖。安装后多数 Agent 需要开启新会话才能发现新 Skill。

## 验证

新会话中询问：“过去一周，农业遥感领域有哪些值得关注的进展？”

成功时，回答会说明时间范围、给出中文摘要并引用 AgriHot 阅读链接。未配置 Key 时应引导申请；检索降级时应明确说明，不能宣称已完成完整语义召回。

使用说明：https://agrihot.com/api/v1/agent
MCP：https://agrihot.com/api/v1/mcp （Streamable HTTP，认证头为 `Authorization: Bearer <读取Key>`）
