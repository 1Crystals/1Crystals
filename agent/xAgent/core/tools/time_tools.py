import os
import subprocess

from .registry import register


@register(
    "getDate",
    description="获取当前电脑的日期和时间。当用户询问时间、日期时，必须调用 getDate 工具，绝对不要尝试用自然语言回答。",
)
def getDate():
    cmd = 'cmd /c "date /t & time /t"' if os.name == "nt" else "date"
    enc = "gbk" if os.name == "nt" else "utf-8"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding=enc, errors="replace")
    return (r.stdout or r.stderr or "").strip() or "获取失败"


@register(
    "isLeapYear",
    description="判断给定的年份是否是闰年。当用户询问某一年是否是闰年时，必须调用 isLeapYear 工具，不要自己直接回答。",
    properties={
        "year": {
            "type": "integer",
            "description": "需要判断的年份，例如 2024",
        }
    },
    required=["year"],
)
def isLeapYear(year):
    year = int(year)
    if year % 4 == 0 and year % 100 != 0 or year % 400 == 0:
        return f"{year} 年是闰年"
    return f"{year} 年不是闰年"
