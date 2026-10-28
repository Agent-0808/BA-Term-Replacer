"""默认配置：密钥、表过滤、OpenCC 模式。"""

# 蔚蓝档案 GL 公开流传的库密钥（PC / Android 相同），可用 --key 覆盖。
DEFAULT_KEY = "ef0aaca06f34b4a4be3172a75a3ea565e815f9ece35b1fb12b7a166ba0807bc4"

# 可能包含玩家可见文本的表（正则，忽略大小写）。
DEFAULT_TABLE_PATTERN = r"Localize|Dialog|Scenario|Subtitle|Talk|Mail|Name|Emoji|Voice"

# OpenCC 模式：tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
# none 只做替换表、不转字形（繁->繁民译用，替换表在阶段 C 接入）。
DEFAULT_CONVERT = "tw2sp"
CONVERT_MODES = ("tw2sp", "t2s", "none")

# 译名对照表默认路径（glossary/ 单层布局）：
# names.tsv 角色名表（exact 整字段匹配），text.tsv 正文替换表（sub 子串匹配）。
DEFAULT_NAMES_GLOSSARY = "glossary/names.tsv"
DEFAULT_TEXT_GLOSSARY = "glossary/text.tsv"
