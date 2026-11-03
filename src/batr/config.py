"""默认配置：密钥、表过滤、OpenCC 模式。"""

# 蔚蓝档案 GL 公开流传的库密钥（PC / Android 相同），可用 --key 覆盖。
DEFAULT_KEY = "ef0aaca06f34b4a4be3172a75a3ea565e815f9ece35b1fb12b7a166ba0807bc4"

# 可能包含玩家可见文本的表（正则，忽略大小写）。
# Messanger 是聊天/Messenger 正文（16120 个中文字段），SNSProfile 是 SNS 简介。
DEFAULT_TABLE_PATTERN = r"Localize|Dialog|Scenario|Subtitle|Talk|Mail|Name|Emoji|Voice|Messanger|SNSProfile"

# OpenCC 模式：tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
# none 只做替换表、不转字形（繁->繁民译用）。
DEFAULT_CONVERT = "tw2sp"
CONVERT_MODES = ("tw2sp", "t2s", "none")

# 译名词表目录（三镜像布局：shared/ 客观共识入库可 PR，local/ 个人偏好不入库，
# templates/ 空模板格式的事实来源）。文件名不承载语义，匹配方式（exact/sub）由
# 注释行 "# mode:" 声明（文件头为第一段缺省值，文件中间可切换、分块混用多种 mode）；
# patch 只读编译产物 compiled.tsv，不再自己拼路径。
GLOSSARY_DIR = "glossary"
GLOSSARY_SHARED = f"{GLOSSARY_DIR}/shared"
GLOSSARY_LOCAL = f"{GLOSSARY_DIR}/local"
GLOSSARY_TEMPLATES = f"{GLOSSARY_DIR}/templates"
GLOSSARY_COMPILED = f"{GLOSSARY_DIR}/compiled.tsv"
GLOSSARY_HITS = f"{GLOSSARY_DIR}/hits.tsv"  # patch 运行时的逐规则命中日志（个人运行数据，不入库）

# 词表 profile：t2s 繁->简（默认，auto 条目编入产物）与 t2t 繁->繁（auto 不编入，
# 手写值必须繁体；patch 端自动绑定 convert=none）。
GLOSSARY_PROFILES = ("t2s", "t2t")
DEFAULT_GLOSSARY_PROFILE = "t2s"

# 输出目录：省略 --out 时，输出库写到 <该目录>/<输入文件名>。
DEFAULT_OUT_DIR = "output"
