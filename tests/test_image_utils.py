"""Issue 019：jiaodui/image_utils.py 单元测试

验证 copy_md_images 在各类场景下的行为正确性。逐字移植旧仓
tests/test_image_utils.py（HEAD 1c45243），仅把导入路径改为 jiaodui.image_utils。
"""
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from jiaodui.image_utils import ImageCopyResult, copy_md_images


@dataclass
class _Fixture:
    """测试夹具：创建临时目录和测试文件。"""
    tmpdir: str
    src_dirs: list[Path]
    target_img_dir: Path

    def create_image(self, filename: str, content: bytes = b"fake-png") -> Path:
        for sd in self.src_dirs:
            p = sd / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            return p
        raise RuntimeError("no src_dirs")


@pytest.fixture
def fx():
    """创建测试夹具。"""
    tmp = tempfile.mkdtemp()
    src1 = Path(tmp) / "src1"
    src2 = Path(tmp) / "src2"
    src1.mkdir(parents=True)
    src2.mkdir(parents=True)
    target = Path(tmp) / "target" / "images"
    yield _Fixture(tmpdir=tmp, src_dirs=[src1, src2], target_img_dir=target)
    shutil.rmtree(tmp, ignore_errors=True)


class TestCopyMdImages:
    """验证 copy_md_images 核心行为。"""

    def test_no_images_returns_unchanged(self, fx):
        """无图片的 Markdown 内容应原样返回。"""
        content = "这是纯文本，没有图片。"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.content == content
        assert result.copied == 0
        assert result.missing == 0

    def test_single_image_copied(self, fx):
        """单张本地图片应被复制到目标目录。"""
        fx.create_image("test.png")
        content = "![测试](./test.png)"

        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)

        assert result.copied == 1
        assert result.missing == 0
        assert "![测试](./images/test.png)" in result.content
        assert (fx.target_img_dir / "test.png").exists()

    def test_http_image_skipped(self, fx):
        """HTTP/HTTPS 图片应跳过，不尝试复制。"""
        content = "![远程](https://example.com/img.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.content == content  # 原样保留
        assert result.copied == 0
        assert result.missing == 0

    def test_http_image_skipped_case_insensitive(self, fx):
        """HTTP 前缀应不区分大小写跳过。"""
        content = "![远程](HTTP://example.com/img.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.content == content  # 原样保留

    def test_search_multiple_src_dirs(self, fx):
        """应在多个源目录中依次查找图片。"""
        sd2 = fx.src_dirs[1]
        (sd2 / "only_in_src2.png").write_bytes(b"img")

        content = "![图](./only_in_src2.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)

        assert result.copied == 1
        assert (fx.target_img_dir / "only_in_src2.png").exists()

    def test_missing_image_counted(self, fx):
        """找不到的图片应计数为 missing。"""
        content = "![不存在](./nonexistent.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.missing == 1
        assert result.copied == 0
        assert result.content == content  # 原样保留

    def test_relative_path_in_src(self, fx):
        """相对路径（如 ./images/xxx.png）应在源目录中查找文件名。"""
        fx.create_image("relative.png")
        content = "![相对](./subdir/relative.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.copied == 1

    def test_mixed_images(self, fx):
        """混合场景：本地图片、HTTP 图片、不存在图片。"""
        fx.create_image("local.png")
        content = (
            "![本地](./local.png)\n"
            "![远程](https://cdn.example/remote.png)\n"
            "![丢失](./missing.png)"
        )
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)

        assert result.copied == 1
        assert result.missing == 1
        assert "./images/local.png" in result.content
        assert "https://cdn.example/remote.png" in result.content  # HTTP 保留
        assert "./missing.png" in result.content  # 丢失的保留

    def test_multiple_same_image_copied_once(self, fx):
        """同一图片多次引用应只复制一次（引用计数仍各算一次）。"""
        fx.create_image("reuse.png")
        content = "![a](./reuse.png)\n![b](./reuse.png)"

        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)

        assert result.copied == 2  # 两次引用都算“成功复制”
        assert (fx.target_img_dir / "reuse.png").exists()

    def test_empty_content(self, fx):
        """空字符串应原样返回。"""
        result = copy_md_images("", fx.src_dirs, fx.target_img_dir)
        assert result.content == ""
        assert result.copied == 0

    def test_custom_relative_path(self, fx):
        """自定义相对路径前缀。"""
        fx.create_image("custom.png")
        content = "![x](./custom.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir, relative_img_path="../img")
        assert "../img/custom.png" in result.content

    def test_target_dir_created(self, fx):
        """目标目录不存在时应自动创建。"""
        fx.create_image("auto.png")
        content = "![x](./auto.png)"
        target = fx.target_img_dir.parent / "nested" / "images"
        assert not target.exists()
        copy_md_images(content, fx.src_dirs, target)
        assert target.exists()

    def test_filename_with_special_chars(self, fx):
        """文件名含空格/中文应正确处理。"""
        fx.create_image("图片 测试.png")
        content = "![图](./图片 测试.png)"
        result = copy_md_images(content, fx.src_dirs, fx.target_img_dir)
        assert result.copied == 1
        assert (fx.target_img_dir / "图片 测试.png").exists()

    def test_result_is_dataclass(self, fx):
        """返回值应为 ImageCopyResult 数据类。"""
        result = copy_md_images("text", fx.src_dirs, fx.target_img_dir)
        assert isinstance(result, ImageCopyResult)
        assert hasattr(result, "content")
        assert hasattr(result, "copied")
        assert hasattr(result, "missing")
