import os
import re
from dataclasses import dataclass

SKILL_DIR_NAMES = (".agentskills", ".agentslskills")
SKILL_FILE_NAME = "SKILL.md"

_FRONTMATTER_KEY = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$")


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: str
    skill_file: str


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _dedent(lines):
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    cut = min(indents) if indents else 0
    return [line[cut:] if len(line) >= cut else "" for line in lines]


def _parse_frontmatter(lines):
    data = {}
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        match = _FRONTMATTER_KEY.match(line)
        if not match:
            i += 1
            continue

        key, rest = match.group(1), match.group(2).strip()
        i += 1

        if rest in ("|", "|-", "|+", ">", ">-", ">+"):
            block = []
            while i < total and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                block.append(lines[i])
                i += 1
            block = _dedent(block)
            if rest.startswith(">"):
                data[key] = " ".join(part.strip() for part in block if part.strip())
            else:
                data[key] = "\n".join(block).strip("\n")
        else:
            data[key] = _unquote(rest)

    return data


def _read_frontmatter(path):
    header = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
        if first.strip() != "---":
            return {}
        for line in f:
            if line.strip() in ("---", "..."):
                break
            header.append(line.rstrip("\r\n"))
    return _parse_frontmatter(header)


def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        raise ValueError("二进制文件")
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _is_within(path, base):
    try:
        return os.path.commonpath(
            [os.path.realpath(path), os.path.realpath(base)]
        ) == os.path.realpath(base)
    except ValueError:
        return False


class SkillManager:
    def __init__(self, root=None):
        self.root = os.path.abspath(root or os.getcwd())
        self.skills = {}

    def discover(self):
        self.skills = {}
        for dir_name in SKILL_DIR_NAMES:
            base = os.path.join(self.root, dir_name)
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base)):
                skill_dir = os.path.join(base, entry)
                if not os.path.isdir(skill_dir):
                    continue
                skill_file = os.path.join(skill_dir, SKILL_FILE_NAME)
                if not os.path.isfile(skill_file):
                    continue
                try:
                    meta = _read_frontmatter(skill_file)
                except OSError:
                    continue
                name = (meta.get("name") or "").strip()
                description = (meta.get("description") or "").strip()
                if not name or not description:
                    continue
                if name in self.skills:
                    continue
                self.skills[name] = SkillInfo(
                    name=name,
                    description=description,
                    path=os.path.abspath(skill_dir),
                    skill_file=os.path.abspath(skill_file),
                )
        return self.skills

    def system_prompt_section(self):
        if not self.skills:
            return ""
        lines = ["You have access to the following skills:"]
        for skill in self.skills.values():
            lines.append(f"- `{skill.name}`: {skill.description}")
        lines.append("")
        lines.append(
            "Use the loadSkill tool to load the full instructions of a skill when needed. "
            "You can also load additional files referenced by a skill."
        )
        return "\n".join(lines)

    def _resolve_file(self, skill, filename):
        filename = filename.replace("\\", os.sep).replace("/", os.sep)
        basename = os.path.basename(filename)

        exact_candidates = []
        if os.path.isabs(filename):
            exact_candidates.append(filename)
        else:
            exact_candidates.append(os.path.join(skill.path, filename))
            project_candidate = os.path.join(self.root, filename)
            if os.path.normpath(project_candidate) not in {
                os.path.normpath(item) for item in exact_candidates
            }:
                exact_candidates.append(project_candidate)

        for candidate in exact_candidates:
            if os.path.isfile(candidate):
                if not _is_within(candidate, skill.path):
                    return None, (
                        f"【错误】文件 {candidate} 不在技能 {skill.name} 的目录内，"
                        "拒绝读取。"
                    )
                return os.path.realpath(candidate), ""

        matches = []
        for dirpath, _dirnames, filenames in os.walk(skill.path):
            for fname in filenames:
                if fname == basename:
                    matches.append(os.path.join(dirpath, fname))

        if len(matches) == 1:
            return os.path.realpath(matches[0]), ""

        if len(matches) > 1:
            lines = [f"找到多个名为 {basename} 的文件，请指定要读取的路径："]
            for match in matches:
                lines.append(f"- {os.path.relpath(match, skill.path)}")
            return None, "\n".join(lines)

        return None, (
            f"【错误】在技能 {skill.name} 的目录中未找到文件：{filename}"
        )

    def load(self, name, filename=None):
        skill = self.skills.get(name)
        if skill is None:
            available = "、".join(sorted(self.skills)) or "（无可用技能）"
            return f"【错误】未找到技能：{name}。可用技能：{available}"

        if filename is None or str(filename).strip() == "":
            try:
                content = _read_text(skill.skill_file)
            except (OSError, ValueError) as e:
                return f"【错误】读取技能 {name} 的说明失败：{e}"
            return f"技能 {name} 的完整说明（{skill.skill_file}）：\n\n{content}"

        target, message = self._resolve_file(skill, str(filename).strip())
        if target is None:
            return message

        try:
            content = _read_text(target)
        except ValueError:
            return f"文件 {target} 不是纯文本文件，暂不支持读取"
        except OSError as e:
            return f"【错误】读取文件失败：{e}"

        relative = os.path.relpath(target, skill.path)
        return f"技能 {name} 的文件 {relative} 内容：\n\n{content}"


_manager = SkillManager()


def get_manager():
    return _manager


def reload_for(root=None):
    _manager.root = os.path.abspath(root or os.getcwd())
    _manager.discover()
    return _manager
