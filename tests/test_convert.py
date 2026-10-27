"""convert.py（OpenCC 繁->简）的固定样例测试。"""
from batr.convert import Converter


def test_t2s_basic() -> None:
    conv = Converter("t2s")
    assert conv.convert("學園的檔案已經損毀") == "学园的档案已经损毁"


def test_tw2sp_phrases() -> None:
    conv = Converter("tw2sp")
    # TWPhrasesRev 用词层 + 单字层，顺序套用
    assert conv.convert("伺服器沒有回應") == "服务器没有回应"
    assert conv.convert("網路連線中斷了") == "网络连接中断了"
    assert conv.convert("收集的資料已儲存完畢") == "收集的数据已保存完毕"


def test_chain_order() -> None:
    # 「資料」先被 TWPhrasesRev 换成「數據」，再被单字层转成「数据」
    conv = Converter("tw2sp")
    assert conv.convert("資料") == "数据"


def test_longest_match_first() -> None:
    conv = Converter("tw2sp")
    # TWPhrasesRev 先把「軟體」换成「软件」（词组优先于单字）
    assert conv.convert("軟體") == "软件"


def test_invalid_mode() -> None:
    try:
        Converter("nope")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
