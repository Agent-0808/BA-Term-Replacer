"""默认配置：密钥、表过滤、OpenCC 模式。"""

# 蔚蓝档案 GL 公开流传的库密钥（PC / Android 相同），可用 --key 覆盖。
DEFAULT_KEY = "ef0aaca06f34b4a4be3172a75a3ea565e815f9ece35b1fb12b7a166ba0807bc4"

# 可能包含玩家可见文本的表（正则，忽略大小写）。
# Messanger 是聊天/Messenger 正文（16120 个中文字段），SNSProfile 是 SNS 简介。
DEFAULT_TABLE_PATTERN = r"Localize|Dialog|Scenario|Subtitle|Talk|Mail|Name|Emoji|Voice|Messanger|SNSProfile"

# OpenCC 模式：tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
# none 只做替换表、不转字形（繁->繁民译用，配合 glossary/*_custom.tsv）。
DEFAULT_CONVERT = "tw2sp"
CONVERT_MODES = ("tw2sp", "t2s", "none")

# 译名对照表默认路径（glossary/ 单层布局，繁->简流程用；繁->繁用 *_custom.tsv 显式传入）：
# names.tsv 角色名表（exact 整字段匹配），text.tsv 正文替换表（sub 子串匹配）。
DEFAULT_NAMES_GLOSSARY = "glossary/names.tsv"
DEFAULT_TEXT_GLOSSARY = "glossary/text.tsv"

# 手工词表（本地，不入库）：写个人偏好的修正/补充，优先于上面自动生成的表（缺省先加载者优先）。
DEFAULT_NAMES_LOCAL = "glossary/names.local.tsv"
DEFAULT_TEXT_LOCAL = "glossary/text.local.tsv"

# 通用专名表（sub 子串匹配，入库共享）：地名/组织/术语的社区通用民译，
# 存在即始终加载（两种模式都生效），个人词条优先级高于它。
DEFAULT_TERMS_GLOSSARY = "glossary/terms.tsv"

# 输出目录：省略 --out 时，输出库写到 <该目录>/<输入文件名>。
DEFAULT_OUT_DIR = "output"
