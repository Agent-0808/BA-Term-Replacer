# cli.py
"""batr 命令行入口：注册子命令并分发（命令实现在 commands/ 包）。"""
from __future__ import annotations

import sys
from typing import Callable

from tap import Tap

from . import __version__
from .commands.export import ExportTap, handle_export
from .commands.glossary import GlossaryTap, handle_glossary
from .commands.patch import PatchTap, handle_patch
from .commands.paths import PathsTap, handle_paths
from .commands.scan import ScanTap, handle_scan


def _setup_stdout() -> None:
    """避免在非 UTF-8 控制台打印中文时报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class MainTap(Tap):
    """主 Tap 类，包含所有子命令。"""

    def configure(self) -> None:
        self.description = f"batr {__version__} — 蔚蓝档案国际服（GL）译名替换 / 繁简转换工具"
        self._underscores_to_dashes = True
        self.add_subparsers(dest="command", help="可用命令")
        self.add_subparser("patch", PatchTap, help="字段级文本补丁 + CRC 修正，--install 可覆盖安装到游戏目录")
        self.add_subparser("scan", ScanTap, help="字段级扫描：关键词定位 / 两库对比 / 未覆盖表清单")
        self.add_subparser("export", ExportTap, help="把数据库文本导出成每表一个 TSV")
        self.add_subparser("glossary", GlossaryTap, help="词表生成：自动表（默认）或自制模板（--template）")
        self.add_subparser("paths", PathsTap, help="显示检测到的游戏安装路径与 ExcelDB.db 路径")


# --- 命令映射 ---
COMMAND_HANDLERS: dict[str, Callable[..., int]] = {
    "patch": handle_patch,
    "scan": handle_scan,
    "export": handle_export,
    "glossary": handle_glossary,
    "paths": handle_paths,
}


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--version" in argv:
        print(f"batr {__version__}")
        return 0
    if not argv:
        MainTap().print_help()
        return 2
    args = MainTap().parse_args(argv)
    handler = COMMAND_HANDLERS.get(getattr(args, "command", None))
    if handler is None:
        MainTap().print_help()
        return 2
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\n已中止（不会留下半成品）")
        return 130
    except Exception as exc:
        print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
