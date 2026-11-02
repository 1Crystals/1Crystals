from .registry import register
from ..skills import get_manager


@register(
    "loadSkill",
    description=(
        "加载指定的 Agent Skill 的完整说明或附件文件。仅提供 name 时读取该技能的 "
        "SKILL.md 全文；同时提供 filename 时读取对应的附件文件（不会重复加载 SKILL.md）。"
        "filename 支持相对于技能目录的路径、项目相对路径或绝对路径。"
    ),
    properties={
        "name": {
            "type": "string",
            "description": "要加载的技能名称，例如 pdf-processing",
        },
        "filename": {
            "type": "string",
            "description": "可选，需要加载的附件文件路径或文件名，例如 reference.md 或 scripts/run.py",
        },
    },
    required=["name"],
)
def loadSkill(name, filename=None):
    return get_manager().load(name, filename)


@register(
    "createSkill",
    description=(
        "根据用户的自然语言要求创建一个新的 Agent Skill。会在当前项目的 "
        ".agents/skills/ 下创建与 name 对应的英文子目录，并生成符合 Agent Skills "
        "规范的 SKILL.md（包含 YAML Frontmatter 的 name、description 和正文）。"
        "若同名 Skill 已存在则不会覆盖。需要额外的 references/、scripts/ 等目录或"
        "辅助文件时，请继续调用文件操作工具创建。"
    ),
    properties={
        "name": {
            "type": "string",
            "description": "Skill 名称，将统一转换为小写字母、数字和连字符组成的英文目录名，例如 pdf-processing",
        },
        "skillContext": {
            "type": "string",
            "description": "要写入 SKILL.md 的完整内容，可包含 Frontmatter 和 Markdown 正文，例如 # 标题、使用步骤等",
        },
    },
    required=["name", "skillContext"],
)
def createSkill(name, skillContext):
    return get_manager().create(name, skillContext)
