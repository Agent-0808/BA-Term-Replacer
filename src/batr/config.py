"""默认配置：密钥、表过滤、OpenCC 模式。"""

# 蔚蓝档案 GL 公开流传的库密钥（PC / Android 相同），可用 --key 覆盖。
DEFAULT_KEY = "ef0aaca06f34b4a4be3172a75a3ea565e815f9ece35b1fb12b7a166ba0807bc4"

# 可能包含玩家可见文本的表（正则，忽略大小写）。
DEFAULT_TABLE_PATTERN = r"Localize|Dialog|Scenario|Subtitle|Talk|Mail|Name|Emoji|Voice"

# OpenCC 模式：tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形。
DEFAULT_CONVERT_MODE = "tw2sp"
CONVERT_MODES = ("tw2sp", "t2s")
