#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-happy-toy-finder 一键自检脚本

核对「2026 麦当劳程序员创意开发大赛」参赛合规要点：
  1. 官方要求的必需文件是否齐全（README.md / CONTEST_DECLARATION.md /
     MCP_INTEGRATION.md / mcp-config.example.json / workbuddy.md）
  2. 源代码目录是否存在
  3. mcp-config.example.json 是否为合法 JSON 且已脱敏（仅环境变量占位符，无真实 Token）
  4. CONTEST_DECLARATION.md 是否包含官方标准章节（防误改）
  5. 仓库是否为 Public（读取 git remote，匿名查询 GitHub API）

退出码：0 = 全部通过；1 = 存在失败项。
无任何第三方依赖，仅使用 Python 标准库。
"""

import json
import os
import re
import subprocess
import sys
import urllib.request

# ---------------------------------------------------------------------- #
# 配置
# ---------------------------------------------------------------------- #
REQUIRED_FILES = [
    ("README.md", "项目介绍（必须，文件名不可改动）"),
    ("CONTEST_DECLARATION.md", "参赛声明（必须，文件名及内容均不可改动）"),
    ("MCP_INTEGRATION.md", "MCP 接入说明（必须，文件名不可改动）"),
    ("mcp-config.example.json", "脱敏 MCP 配置示例（必须，仅环境变量占位符）"),
    ("workbuddy.md", "WorkBuddy 开发上下文（参加专项奖励时必须）"),
]

# 参赛声明必须包含的官方章节标题
DECLARATION_SECTIONS = [
    "原创性声明", "合规声明", "信息安全声明", "规则遵守声明",
]

# 疑似真实 Token 的正则（Bearer 后跟非占位符的长字符串）
REAL_TOKEN = re.compile(r"Bearer\s+(?![\$\{])[A-Za-z0-9_\-]{16,}")

GREEN, RED, YELLOW, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def c(text, color):
    # Windows 旧终端可能不支持 ANSI，简单包裹即可
    return f"{color}{text}{RESET}"


def mark(ok):
    return c("✅", GREEN) if ok else c("❌", RED)


def warn_mark():
    return c("⚠️", YELLOW)


def file_exists(root, name):
    return os.path.isfile(os.path.join(root, name))


def check_required_files(root):
    print("\n=== 1) 必需文件齐全性 ===")
    all_ok = True
    for name, desc in REQUIRED_FILES:
        ok = file_exists(root, name)
        all_ok = all_ok and ok
        print(f"  {mark(ok)} {name}  — {desc}")
    # 源代码目录
    scripts_dir = os.path.join(root, "scripts")
    src_ok = os.path.isdir(scripts_dir) and any(
        f.endswith(".py") for f in os.listdir(scripts_dir)
    ) if os.path.isdir(scripts_dir) else False
    all_ok = all_ok and src_ok
    print(f"  {mark(src_ok)} scripts/  —— 源代码（必须，形式不限）")
    return all_ok


def check_config_desensitized(root):
    print("\n=== 2) mcp-config.example.json 脱敏校验 ===")
    path = os.path.join(root, "mcp-config.example.json")
    if not os.path.isfile(path):
        print(f"  {mark(False)} 文件不存在，跳过")
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  {mark(False)} JSON 解析失败：{e}")
        return False
    print(f"  {mark(True)} JSON 格式合法")

    # 序列化为文本做 Token 扫描
    text = json.dumps(data, ensure_ascii=False)
    leaked = REAL_TOKEN.search(text)
    if leaked:
        print(f"  {mark(False)} 检测到疑似真实 Token：{leaked.group(0)[:12]}…（请改为环境变量占位符）")
        return False
    print(f"  {mark(True)} 未检测到真实 Token")

    # 是否使用了环境变量占位符 ${...}
    if "${" in text:
        print(f"  {mark(True)} 使用了环境变量占位符（${'…'}）")
        return True
    else:
        print(f"  {warn_mark()} 未检测到 ${'…'} 占位符，请确认配置已脱敏")
        return False


def check_declaration(root):
    print("\n=== 3) CONTEST_DECLARATION.md 章节完整性 ===")
    path = os.path.join(root, "CONTEST_DECLARATION.md")
    if not os.path.isfile(path):
        print(f"  {mark(False)} 文件不存在")
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    missing = [s for s in DECLARATION_SECTIONS if s not in content]
    if missing:
        print(f"  {mark(False)} 缺少官方章节：{', '.join(missing)}")
        return False
    print(f"  {mark(True)} 包含全部官方标准章节：{', '.join(DECLARATION_SECTIONS)}")
    return True


def get_remote_repo():
    try:
        out = subprocess.run(
            ["git", "-C", ROOT, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        url = out.stdout.strip()
    except Exception:
        return None
    # 支持 https 与 ssh 两种形式
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?", url)
    if m:
        return m.group(1), m.group(2)
    return None


def check_public(root):
    print("\n=== 4) 仓库是否为 Public ===")
    repo = get_remote_repo()
    if not repo:
        print(f"  {warn_mark()} 未检测到 git remote 'origin'，无法自动判断公开状态")
        print(f"  {warn_mark()} 请手动确认仓库已设为 Public")
        return None
    owner, name = repo
    print(f"  检测到远程仓库：{owner}/{name}")
    api = f"https://api.github.com/repos/{owner}/{name}"
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "selfcheck"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  {mark(False)} 匿名访问返回 404 —— 仓库不可公开访问（可能仍为 Private）")
            return False
        print(f"  {warn_mark()} 查询失败（HTTP {e.code}），请手动确认")
        return None
    except Exception as e:
        print(f"  {warn_mark()} 网络查询失败：{e}，请手动确认")
        return None

    if data.get("private") is False:
        print(f"  {mark(True)} 仓库为 Public，匿名可访问 ✅")
        return True
    else:
        print(f"  {mark(False)} 仓库仍为 Private，请到 GitHub 设置为 Public")
        return False


def main():
    global ROOT
    ROOT = os.path.dirname(os.path.abspath(__file__))
    print(c("🍔 mcd-happy-toy-finder 参赛合规自检", GREEN))
    print(f"仓库根目录：{ROOT}")

    results = []
    results.append(("必需文件", check_required_files(ROOT)))
    results.append(("配置脱敏", check_config_desensitized(ROOT)))
    results.append(("声明完整", check_declaration(ROOT)))
    public = check_public(ROOT)
    if public is not None:
        results.append(("仓库公开", public))

    print("\n================ 结论 ================")
    failed = [name for name, ok in results if ok is False]
    warned = [name for name, ok in results if ok is None]

    for name, ok in results:
        if ok is True:
            print(f"  {mark(True)} {name}")
        elif ok is False:
            print(f"  {mark(False)} {name}")
        else:
            print(f"  {warn_mark()} {name}（需手动确认）")

    print()
    if failed:
        print(c(f"❌ 自检未通过，请修复以下项：{', '.join(failed)}", RED))
        sys.exit(1)
    elif warned:
        print(c("⚠️ 基本通过，但有以下项需你手动确认（通常是网络/权限导致无法自动判定）。", YELLOW))
        sys.exit(0)
    else:
        print(c("✅ 全部通过！可安心提交/重新报名。", GREEN))
        sys.exit(0)


if __name__ == "__main__":
    main()
