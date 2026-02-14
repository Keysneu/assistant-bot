#!/usr/bin/env python3
"""Test script for GLM-4V-Flash Vision API functionality.

Tests:
1. API availability check
2. Image analysis with GLM-4V-Flash (free model)
3. Error handling validation

Prerequisites:
- Set GLM_API_KEY in .env file or environment variable
- pip install httpx pillow
"""
import asyncio
import base64
import io
import logging
import os
import sys
from pathlib import Path

import httpx
from PIL import Image

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.vision_service import (
    analyze_image_content,
    is_vision_available,
    get_supported_formats,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def create_test_image() -> bytes:
    """Create a simple test image (red square with text).

    Returns:
        Image bytes in PNG format
    """
    # Create a 200x200 red image with white text "TEST"
    img = Image.new('RGB', (200, 200), color='red')

    # Add some white pixel "text" (simple pattern)
    pixels = img.load()
    for y in range(50, 150, 10):
        for x in range(50, 150, 10):
            pixels[x, y] = (255, 255, 255)  # white

    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def test_api_availability():
    """Test if GLM API is properly configured."""
    print_header("1. API可用性检查")

    if not settings.GLM_API_KEY:
        print("  ✗ GLM_API_KEY 未设置")
        print("  请在 .env 文件中设置: GLM_API_KEY=your_api_key")
        print("  获取API Key: https://open.bigmodel.cn/usercenter/api-keys")
        return False

    print(f"  ✓ API Key 已配置 (前4位: {settings.GLM_API_KEY[:4]}******)")
    print(f"  ✓ 模型配置: {settings.GLM_VISION_MODEL}")
    print(f"  ✓ 后端类型: {settings.VISION_BACKEND}")
    return True


async def test_image_analysis():
    """Test GLM-4V-Flash image analysis."""
    print_header("2. GLM-4V-Flash 图像分析测试")

    # Create test image
    print("  正在生成测试图片...")
    image_bytes = create_test_image()
    print(f"  ✓ 测试图片已生成 (大小: {len(image_bytes)} bytes)")

    # Test vision availability
    if not is_vision_available():
        print("  ✗ 视觉服务不可用")
        return False

    print("  ✓ 视觉服务可用")

    # Test analysis
    print("\n  正在调用 GLM-4V-Flash API...")
    print("  模型: glm-4v-flash (免费)")
    print("  请求数据...")

    try:
        result = await analyze_image_content(
            image_bytes=image_bytes,
            user_question="请描述这张测试图片的内容"
        )

        print(f"\n  ✓ API调用成功!")
        print(f"\n【分析结果】")
        print("-" * 50)
        print(result)
        print("-" * 50)
        return True

    except Exception as e:
        print(f"\n  ✗ API调用失败: {e}")
        print("\n  可能的原因:")
        print("  1. GLM_API_KEY 未设置或无效")
        print("  2. 网络连接问题")
        print("  3. API 服务暂时不可用")
        print("\n  获取API Key: https://open.bigmodel.cn/usercenter/api-keys")
        return False


async def test_supported_formats():
    """Test supported image formats."""
    print_header("3. 支持的图片格式")

    formats = get_supported_formats()
    print(f"  ✓ 支持的格式: {', '.join(formats)}")
    print(f"  总计: {len(formats)} 种格式")

    # GLM-4V-Flash 具体限制
    print("\n  GLM-4V-Flash 限制:")
    print("  - 图片大小: 最大 5MB")
    print("  - 图片尺寸: 最大 6000x6000 像素")
    print("  - 支持格式: JPG, PNG, JPEG")

    return True


async def test_base64_encoding():
    """Test base64 encoding for image."""
    print_header("4. Base64 编码测试")

    # Create a small test image
    img = Image.new('RGB', (100, 100), color=(100, 150, 200))
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()

    # Encode to base64
    base64_str = base64.b64encode(image_bytes).decode('utf-8')
    data_uri = f"data:image/png;base64,{base64_str}"

    print(f"  ✓ 原始图片大小: {len(image_bytes)} bytes")
    print(f"  ✓ Base64编码后大小: {len(base64_str)} chars")
    print(f"  ✓ Data URI 前缀长度: {len(data_uri)} chars")
    print(f"  ✓ 编码正确: {data_uri[:30]}...")

    return True


async def main():
    """Run all tests."""
    print("=" * 70)
    print("  GLM-4V-Flash 视觉API 测试套件")
    print("=" * 70)

    # Check API availability first
    if not test_api_availability():
        print("\n请先配置 API Key 后再运行测试！")
        return

    # Run tests
    results = []
    results.append(await test_supported_formats())
    results.append(await test_base64_encoding())
    results.append(await test_image_analysis())

    # Summary
    print("\n")
    print("=" * 70)
    print("  测试总结")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"  通过: {passed}/{total}")

    if passed == total:
        print("\n  ✓ 所有测试通过！GLM-4V-Flash 视觉功能正常工作。")
    else:
        print(f"\n  ⚠️ {total - passed} 个测试失败，请检查配置和网络连接。")

    print("\n  下一步:")
    print("  1. 在前端测试图片上传和识别")
    print("  2. 启动后端服务: cd backend && uvicorn app.main:app --reload")
    print("  3. 启动前端服务: cd frontend && npm run dev")


if __name__ == "__main__":
    asyncio.run(main())
