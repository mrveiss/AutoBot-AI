#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script to reproduce the Ollama timeout issue
"""
import asyncio
import aiohttp
import json
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ollama_streaming():
    """Test the exact same request that hangs in the backend"""
    url = "http://127.0.0.1:11434/api/chat"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "llama3.2:1b-instruct-q4_K_M",
        "messages": [
            {
                "role": "system",
                "content": "You are AutoBot, an intelligent Linux automation assistant with access to comprehensive documentation and knowledge base.\n\nYou have multi-agent architecture with the following capabilities:\n- System Administration: Linux commands, file management, process control\n- Workflow Automation: Template creation, scheduling, and execution\n- Knowledge Integration: AI-powered documentation search and retrieval\n- Enterprise Features: Scalable and monitored automation solutions\n\nYou can access LlamaIndex vectors in Redis, LangChain data, and semantic search capabilities for authoritative responses.\n\nAlways provide accurate, helpful information based on your knowledge base when available."
            },
            {
                "role": "system", 
                "content": "Test knowledge context"
            },
            {
                "role": "user",
                "content": "hello"
            }
        ],
        "stream": True,
        "temperature": 0.7,
        "format": "",
        "options": {
            "seed": 42,
            "top_k": 40,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_ctx": 4096
        }
    }

    print("Starting Ollama test...")
    print(f"Request URL: {url}")
    print(f"Request Headers: {headers}")
    print(f"Request Data: {json.dumps(data, indent=2)}")
    
    start_time = time.time()
    
    try:
        # Test with 15-second timeout like SimpleChatWorkflow
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("Session created, making POST request...")
            
            async with session.post(url, headers=headers, json=data) as response:
                print(f"Response received, status: {response.status}")
                response.raise_for_status()
                
                # Handle streaming response
                full_content = ""
                chunk_count = 0
                max_chunks = 100
                stream_start = time.time()
                stream_timeout = 10.0
                
                print("Starting to process streaming chunks...")
                async for line in response.content:
                    current_time = time.time()
                    elapsed = current_time - stream_start
                    
                    print(f"Processing chunk {chunk_count}, elapsed: {elapsed:.2f}s")
                    
                    if elapsed > stream_timeout:
                        logger.warning(f"Stream timeout exceeded ({stream_timeout}s), breaking stream")
                        break
                    
                    chunk_count += 1
                    if chunk_count > max_chunks:
                        logger.warning(f"Max chunks exceeded ({max_chunks}), breaking stream")
                        break
                    
                    line_text = line.decode("utf-8").strip()
                    if line_text:
                        try:
                            chunk = json.loads(line_text)
                            if "message" in chunk and "content" in chunk["message"]:
                                content = chunk["message"]["content"]
                                full_content += content
                                print(f"Chunk content: '{content}'")
                            
                            if chunk.get("done", False):
                                print(f"Done chunk received!")
                                print(f"Final response: {full_content}")
                                return {
                                    "model": chunk.get("model"),
                                    "message": {"role": "assistant", "content": full_content},
                                    "done": True
                                }
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                            continue
                
                # Fallback if no done chunk
                print(f"No done chunk received, returning content: {full_content}")
                return {
                    "message": {"role": "assistant", "content": full_content},
                    "done": True
                }
                
    except asyncio.TimeoutError as e:
        print(f"TIMEOUT ERROR: {e}")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None
    finally:
        end_time = time.time()
        print(f"Total time: {end_time - start_time:.2f} seconds")

async def main():
    """Run the test"""
    print("=== Ollama Streaming Test ===")
    result = await test_ollama_streaming()
    print(f"=== Test Result: {result} ===")

if __name__ == "__main__":
    asyncio.run(main())