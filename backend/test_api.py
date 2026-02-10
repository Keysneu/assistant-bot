#!/usr/bin/env python3
"""API 测试脚本 - 演示基本对话和 RAG 功能

运行前请确保后端服务已启动:
    cd backend && uvicorn app.main:app --reload
"""

import requests
import json
import time


API_BASE = "http://localhost:8000/api"


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_health():
    """测试健康检查"""
    print_section("1. 健康检查")
    response = requests.get(f"{API_BASE}/health/")
    data = response.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def test_basic_chat():
    """测试基本对话（无 RAG）"""
    print_section("2. 基本对话测试（无 RAG）")

    questions = [
        "Hello",
        "你好",
        "What is the capital of France?",
    ]

    for q in questions:
        print(f"用户: {q}")
        response = requests.post(
            f"{API_BASE}/chat/",
            json={"message": q, "stream": False},
            timeout=60
        )
        data = response.json()
        print(f"助手: {data['content']}")
        print(f"  (使用 RAG: {data['metadata'].get('use_rag', False)})")
        print()


def test_rag_chat():
    """测试 RAG 对话"""
    print_section("3. RAG 对话测试（基于文档）")

    questions = [
        "What is ROSE Vision Lab?",
        "ROSE Vision Lab 研究什么？",
    ]

    for q in questions:
        print(f"用户: {q}")
        response = requests.post(
            f"{API_BASE}/chat/",
            json={"message": q, "stream": False},
            timeout=60
        )
        data = response.json()
        print(f"助手: {data['content']}")

        if data.get('sources'):
            print(f"\n  引用来源:")
            for i, source in enumerate(data['sources'][:2], 1):
                print(f"    {i}. {source['source']} (相关度: {source['score']:.2%})")
        print()


def test_documents():
    """测试文档管理"""
    print_section("4. 文档管理测试")

    # 获取文档列表
    response = requests.get(f"{API_BASE}/documents/list")
    data = response.json()

    print(f"文档统计:")
    print(f"  总文档数: {data['total_count']}")
    print(f"  总分块数: {data['total_chunks']}")

    if data['documents']:
        print(f"\n文档列表:")
        for doc in data['documents']:
            print(f"  - {doc['source']} ({doc['chunk_count']} 个分块)")


def main():
    """主函数"""
    print("\n🤖 AssistantBot API 测试\n")

    try:
        # 测试健康检查
        health = test_health()

        if health.get('status') != 'healthy':
            print("\n⚠️  警告: 服务未完全就绪，首次请求可能会较慢...")

        time.sleep(1)

        # 测试基本对话
        test_basic_chat()

        # 测试文档
        test_documents()

        # 测试 RAG 对话
        test_rag_chat()

        print("\n✅ 所有测试完成！\n")

    except requests.exceptions.ConnectionError:
        print("\n❌ 错误: 无法连接到后端服务")
        print("\n请先启动后端服务:")
        print("  cd backend && uvicorn app.main:app --reload\n")
    except Exception as e:
        print(f"\n❌ 错误: {e}\n")


if __name__ == "__main__":
    main()
