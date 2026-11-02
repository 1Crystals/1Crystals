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
