#!/usr/bin/env python3
"""Test script for GLM-4V Vision API functionality.

Tests:
1. Health check
2. GLM Vision API - analyze image
3. Sessions API - verify image data storage
"""
import base64
import json
import requests
import sys

API_BASE = "http://localhost:8000/api/chat"

def print_header(title: str):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_health_check():
    """Test health check endpoint."""
    print_header("1. Health Check API")
    try:
        response = requests.get(f"{API_BASE}/../health", timeout=5)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Status: {data.get('status', 'UNKNOWN')}")
            print(f"  ✓ Backend ready: {data.get('model_loaded', False)}")
        else:
            print(f"  ✗ Unexpected status code")
    except Exception as e:
        print(f"  ✗ Error: {e}")

def test_glm_vision():
    """Test GLM-4V Vision API with a sample image."""
    print_header("2. GLM Vision API Test")

    # Create a simple test image (1x1 red pixel)
    # This is just a test - using a real image would require GLM API
    test_image_b64 = "iVBORw0KGgoAAAANSUhEUAAAMQAAADsAQAIAAIAAMQAAAgQBGQAAYABgMCOCO2CwCO2CAwQBAQOAMGOxEAMAAAAA4wAAMQAAOGxAOMA4wDMAMAMAMwAAAAA8wMAMAMwAAAMAAMwAAAAAAAAAAAAAwAAAAAAAAAAAAAI8wMAAAAAAAAP/////////////////8wAAMAAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMQA4QIIAAAAAAAAA4wDMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMAMgA"

    # Test vision API
    try:
        response = requests.post(f"{API_BASE}/stream",
            json={
                "message": "请描述这张图片",
                "image": test_image_b64,
                "image_format": "png",
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        print(f"  Request sent, status: {response.status_code}")

        if response.status_code == 200:
            print(f"  Streaming response received")

            # Read SSE stream
            full_response = ""
            for line in response.iter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if "event" in data:
                            if data["event"] == "token":
                                full_response += data["data"].get("token", "") + " "
                            elif data["event"] == "done":
                                result_data = data["data"]
                                print(f"  Done! Full response: {result_data.get('full_content', '')[:100]}...")
                                break
                        elif data["event"] == "error":
                                print(f"  ✗ Error: {data['data'].get('error', 'Unknown error')}")
                                break
                    elif line.startswith("event:metadata"):
                        # Skip metadata events for now
                        pass

            print(f"  Full response length: {len(full_response)} chars")

    else:
            print(f"  ✗ Unexpected status code: {response.status_code}")

    except Exception as e:
        print(f"  ✗ Error: {e}")

def test_sessions_image_storage():
    """Test if image data is properly stored in sessions."""
    print_header("3. Sessions API - Image Storage Test")

    try:
        response = requests.get(f"{API_BASE}/sessions", timeout=5)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            sessions = response.json().get("sessions", [])
            print(f"  ✓ Found {len(sessions)} sessions")

            # Check if any session has image data
            found_image = False
            for session in sessions[:3]:  # Check first 3 sessions
                messages = session.get("messages", [])
                for msg in messages:
                    if msg.get("has_image") or msg.get("image_data"):
                        found_image = True
                        print(f"  ✓ Session '{session.get('id')}' has image: {msg.get('role', 'user')}")
                        if msg.get("image_data"):
                            print(f"    - Image format: {msg.get('image_format', 'unknown')}")
                            print(f"    - Image data length: {len(msg.get('image_data', ''))} chars")
                            break
                if found_image:
                    break

            if not found_image:
                print(f"  ✗ No image data found in recent sessions")
        else:
            print(f"  ✗ Unexpected status code: {response.status_code}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

def main():
    """Run all tests."""
    print("=" * 80)
    print("  AssistantBot Backend - Full Test Suite")
    print("=" * 80)

    test_health_check()
    print()
    test_glm_vision()
    print()
    test_sessions_image_storage()

    print()
    print("=" * 80)
    print("\n所有测试完成！")
    print("  请在前端验证:")
    print("  1. 打开浏览器开发者工具控制台")
    print("  2. 访问 http://localhost:5173")
    print("  3. 测试发送消息（带图片）")
    print("  4. 检查会话列表中是否保存了图片数据")

if __name__ == "__main__":
    main()
