#!/usr/bin/env python3
"""
Test script for Code Interpreter Agent
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_interpreter_agent import CodeInterpreterAgent

def test_agent():
    """Test the Code Interpreter Agent with the demo database"""

    # Initialize the agent with the demo database
    agent = CodeInterpreterAgent(db_path="demo.db")

    print("=== Code Interpreter Agent Test ===")
    print("Database:", agent.db_path)
    print()

    # Test 1: Get database schema
    print("1. Testing database schema retrieval...")
    try:
        schema = agent.tools["get_schema"]()
        print("Schema retrieval successful!")
        print("Schema length:", len(schema) if isinstance(schema, str) else "N/A")
        print()
    except Exception as e:
        print(f"Schema retrieval failed: {e}")
        print()

    # Test 2: Simple query (fallback mode)
    print("2. Testing simple query...")
    try:
        result = agent.run("你好")
        print("Query result:")
        print(result)
        print()
    except Exception as e:
        print(f"Query failed: {e}")
        print()

    # Test 3: Reset agent
    print("3. Testing agent reset...")
    try:
        agent.reset()
        print("Agent reset successful!")
        print()
    except Exception as e:
        print(f"Agent reset failed: {e}")
        print()

    print("=== Test Complete ===")

if __name__ == "__main__":
    test_agent()