"""pytest 根 conftest：把仓库根加入 sys.path，使 tests 无需安装即可导入 jiaodui。"""
import sys
import tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """旧确定性用例显式授权自己的临时工作区，临时资源也限定在其中。"""
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
