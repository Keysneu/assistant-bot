#!/usr/bin/env python3
"""RAG 准确性测试脚本

测试 RAG 系统的以下能力：
1. 准确回答文档中的问题
2. 拒绝回答文档外的问题（不胡乱回答）

运行前请确保后端服务已启动:
    cd backend && uvicorn app.main:app --reload
"""

import requests
import json

API_BASE = "http://localhost:8000/api"


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_rag_accuracy():
    """测试 RAG 准确性"""
    print_section("RAG 准确性测试")

    # 测试用例：包含文档中的问题和文档外的问题
    test_cases = [
        {
            "category": "文档内容相关问题（应该准确回答）",
            "questions": [
                "ROSE Vision Lab 的主要研究方向是什么？",
                "马勇俐是在哪里上的大学？",
                "ROSE 实验室的全称是什么？",
            ]
        },
        {
            "category": "文档外问题（应该说明无法回答）",
            "questions": [
                "什么是量子计算？",
                "2024年奥运会在哪里举办？",
                "特斯拉的股票价格是多少？",
            ]
        },
    ]

    results = {
        "document_qa": [],
        "out_of_scope_qa": [],
    }

    for test_group in test_cases:
        print(f"\n【{test_group['category']}】")
        print("-" * 70)

        for question in test_group["questions"]:
            print(f"\n问题: {question}")

            try:
                response = requests.post(
                    f"{API_BASE}/chat/",
                    json={"message": question, "stream": False},
                    timeout=120
                )

                if response.status_code == 200:
                    data = response.json()
                    answer = data.get('content', '')

                    print(f"回答: {answer}")

                    # 记录结果
                    result_entry = {
                        "question": question,
                        "answer": answer,
                        "sources": data.get('sources', []),
                    }

                    if "文档外" in test_group['category']:
                        results["out_of_scope_qa"].append(result_entry)
                        # 检查是否正确拒绝回答
                        if any(keyword in answer for keyword in [
                            "无法回答", "没有提供", "文档中没有",
                            "不知道", "无法提供", "没有信息"
                        ]):
                            print("  ✓ 正确拒绝回答")
                        else:
                            print("  ⚠ 应该拒绝回答但给出了答案")
                    else:
                        results["document_qa"].append(result_entry)
                        print(f"  来源数: {len(data.get('sources', []))}")
                else:
                    print(f"  ✗ 请求失败: {response.status_code}")

            except Exception as e:
                print(f"  ✗ 错误: {e}")

    # 输出测试总结
    print_section("测试总结")
    print(f"文档相关问题: {len(results['document_qa'])} 个")
    print(f"文档外问题: {len(results['out_of_scope_qa'])} 个")

    # 评估文档外问题的拒绝率
    if results["out_of_scope_qa"]:
        refused = sum(
            1 for r in results["out_of_scope_qa"]
            if any(keyword in r["answer"] for keyword in [
                "无法回答", "没有提供", "文档中没有",
                "不知道", "无法提供", "没有信息"
            ])
        )
        refusal_rate = refused / len(results["out_of_scope_qa"]) * 100
        print(f"\n文档外问题正确拒绝率: {refusal_rate:.1f}% ({refused}/{len(results['out_of_scope_qa'])})")

    return results


def test_retrieval_quality():
    """测试检索质量"""
    print_section("检索质量测试")

    test_queries = [
        "马勇俐的教育背景",
        "ROSE Vision Lab 研究方向",
        "实验室研究成果",
    ]

    for query in test_queries:
        print(f"\n查询: {query}")

        try:
            response = requests.post(
                f"{API_BASE}/chat/",
                json={"message": query, "stream": False},
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                sources = data.get('sources', [])

                print(f"  检索到 {len(sources)} 个相关文档:")

                for i, source in enumerate(sources[:5], 1):
                    score = source.get('score', 0)
                    source_name = source.get('source', 'Unknown')
                    content_preview = source.get('content', '')[:100]
                    print(f"    {i}. [{source_name}] (相关度: {score:.2%})")
                    print(f"       {content_preview}...")
            else:
                print(f"  ✗ 请求失败: {response.status_code}")

        except Exception as e:
            print(f"  ✗ 错误: {e}")


def main():
    """主函数"""
    print("\n🔍 RAG 准确性测试\n")

    # 先检查服务状态
    try:
        response = requests.get(f"{API_BASE}/health/", timeout=5)
        health = response.json()
        print(f"服务状态: {health.get('status', 'unknown')}")
        print(f"文档库就绪: {health.get('vector_db_ready', False)}")

        if health.get('status') != 'healthy' and health.get('status') != 'initializing':
            print("\n⚠️  服务未完全就绪，首次请求可能会较慢...")

    except requests.exceptions.ConnectionError:
        print("\n❌ 错误: 无法连接到后端服务")
        print("\n请先启动后端服务:")
        print("  cd backend && uvicorn app.main:app --reload\n")
        return

    print("\n开始测试...")

    # 测试检索质量
    test_retrieval_quality()

    # 测试 RAG 准确性
    test_rag_accuracy()

    print("\n✅ 测试完成！\n")


if __name__ == "__main__":
    main()
