# commands/paths.py
"""paths 子命令：显示检测到的游戏安装路径与 ExcelDB.db 路径（排查自动定位问题用）。"""
from ..utils.paths import BARegion, get_BA_path, get_excel_db_path
from .base import BaseTap


class PathsTap(BaseTap):
    """显示检测到的游戏安装路径与 ExcelDB.db 路径。"""

    region: BARegion = "auto"  # auto = 显示 global 与 japan 两个区服


def handle_paths(args: PathsTap) -> int:
    """处理 paths 子命令（args 为合并了子命令属性的主 namespace）。"""
    regions = ("global", "japan") if args.region == "auto" else (args.region,)
    found = False
    for r in regions:
        root = get_BA_path(r)
        db_path = get_excel_db_path(r)
        found = found or (db_path is not None)
        print(f"[{r}] 游戏目录:   {root or '未找到'}")
        print(f"[{r}] ExcelDB.db: {db_path or '未找到'}")
    return 0 if found else 1
