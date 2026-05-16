#!/usr/bin/env python3
"""Test script to verify chat_id persistence across multiple queries."""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_chat_persistence():
    """Test that chat_id persists across multiple queries in the same conversation."""
    
    print("=" * 60)
    print("Testing Chat ID Persistence")
    print("=" * 60)
    
    # Step 0: Register and login to get token
    print("\n0. Registering and logging in...")
    username = "test_user_chat_persistence"
    password = "test_password_123"
    
    # Try to register
    register_payload = {"username": username, "password": password}
    requests.post(f"{BASE_URL}/register", json=register_payload)  # ignore response
    
    # Login
    login_response = requests.post(f"{BASE_URL}/login", json=register_payload)
    if login_response.status_code != 200:
        print(f"   ❌ ERROR: Login failed with status {login_response.status_code}")
        print(f"   Response: {login_response.text}")
        return False
    
    token = login_response.json().get("token") or login_response.json().get("access_token")
    if not token:
        print(f"   ❌ ERROR: No token returned from login")
        print(f"   Response: {login_response.json()}")
        return False
    
    print(f"   ✅ Logged in successfully")
    headers = {"Authorization": f"Bearer {token}"}
    
    # First query - no chat_id provided, backend should generate one
    print("\n1. First query (no chat_id) - backend should generate one:")
    query1_payload = {
        "question": "What is artificial intelligence?",
        "chat_history": []
    }
    
    response1 = requests.post(f"{BASE_URL}/query", json=query1_payload, headers=headers)
    data1 = response1.json()
    chat_id_from_first = data1.get("chat_id")
    
    print(f"   Response status: {response1.status_code}")
    print(f"   Generated chat_id: {chat_id_from_first}")
    print(f"   Answer preview: {data1.get('answer', '')[:100]}...")
    
    if not chat_id_from_first:
        print("   ❌ ERROR: No chat_id returned from first query!")
        return False
    
    # Second query - WITH the chat_id from first response
    print(f"\n2. Second query (with chat_id={chat_id_from_first[:8]}...)")
    query2_payload = {
        "question": "How does machine learning work?",
        "chat_id": chat_id_from_first,
        "chat_history": [
            {"role": "user", "content": "What is artificial intelligence?"},
            {"role": "assistant", "content": data1.get("answer", "...")}
        ]
    }
    
    response2 = requests.post(f"{BASE_URL}/query", json=query2_payload, headers=headers)
    data2 = response2.json()
    chat_id_from_second = data2.get("chat_id")
    
    print(f"   Response status: {response2.status_code}")
    print(f"   Returned chat_id: {chat_id_from_second}")
    print(f"   Answer preview: {data2.get('answer', '')[:100]}...")
    
    # Verify same chat_id
    print(f"\n3. Verification:")
    if chat_id_from_second == chat_id_from_first:
        print(f"   ✅ SUCCESS: Both queries returned the SAME chat_id!")
        print(f"   Chat ID: {chat_id_from_first}")
        return True
    else:
        print(f"   ❌ ERROR: chat_ids don't match!")
        print(f"   First:  {chat_id_from_first}")
        print(f"   Second: {chat_id_from_second}")
        return False

if __name__ == "__main__":
    try:
        success = test_chat_persistence()
        print("\n" + "=" * 60)
        if success:
            print("Test PASSED ✅")
        else:
            print("Test FAILED ❌")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test Error: {e}")
        print("=" * 60)
