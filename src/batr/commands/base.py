# commands/base.py
"""各子命令 Tap 的共享基类。"""

from tap import Tap


class BaseTap(Tap):
    """基础 Tap 类，提供共享配置。"""

    def configure(self) -> None:
        self._underscores_to_dashes = True
