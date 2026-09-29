"""pytest 根 conftest：把仓库根加入 sys.path，使 tests 无需安装即可导入 jiaodui。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
