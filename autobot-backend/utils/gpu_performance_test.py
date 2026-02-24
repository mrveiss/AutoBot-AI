#!/usr/bin/env python3
"""
Performance test for AutoBot GPU optimization
Tests semantic chunking performance and identifies optimization opportunities.
"""

import asyncio
import sys
import time

import psutil
import torch

# Add AutoBot to path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")

from utils.semantic_chunker import AutoBotSemanticChunker

# Sample text for performance testing
TEST_TEXT = (
    """
Artificial intelligence has revolutionized countless industries and aspects of human life.
Machine learning algorithms can now process vast amounts of data with unprecedented speed and accuracy.
Neural networks, inspired by the human brain, have enabled computers to recognize patterns, understand language, and make complex decisions.

Deep learning, a subset of machine learning, has particularly transformed fields like computer vision and natural language processing.
Convolutional neural networks excel at image recognition tasks, while transformer architectures have revolutionized language understanding.
These advances have enabled applications from autonomous vehicles to sophisticated chatbots.

The development of large language models represents a significant milestone in AI progress.
These models, trained on enormous datasets, can generate human-like text, answer questions, and even write code.
However, they also raise important questions about bias, misinformation, and the future role of AI in society.

Cloud computing has made AI more accessible to businesses and researchers worldwide.
Powerful GPUs and specialized AI chips accelerate training and inference processes.
Edge computing brings AI capabilities directly to devices, enabling real-time processing without constant internet connectivity.

The ethical implications of AI continue to evolve as the technology becomes more powerful and pervasive.
Questions about privacy, job displacement, and algorithmic fairness require careful consideration.
Responsible AI development involves transparency, accountability, and inclusive design practices.

Future developments in quantum computing may further accelerate AI capabilities.
Quantum algorithms could solve certain computational problems exponentially faster than classical computers.
The intersection of quantum computing and artificial intelligence represents an exciting frontier in technology.
"""
    * 3
)  # Triple the text for more substantial processing


async def measure_gpu_utilization():
    """Measure GPU utilization during processing."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            values = result.stdout.strip().split(",")
            return {
                "gpu_util": float(values[0].strip()),
                "memory_used": float(values[1].strip()),
                "memory_total": float(values[2].strip()),
                "temperature": float(values[3].strip()),
                "power": float(values[4].strip()),
            }
    except Exception:
        pass

    return None


async def performance_test():
    """Run comprehensive performance test."""
    print("=== AutoBot GPU Performance Analysis ===\n")  # noqa: print

    # System info
    print("Hardware Configuration:")  # noqa: print
    print(f"- CPU: Intel Ultra 9 185H ({psutil.cpu_count()} cores)")  # noqa: print
    print(  # noqa: print
        f"- GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}"
    )
    print(  # noqa: print
        f"- GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
    )
    print(  # noqa: print
        f"- System Memory: {psutil.virtual_memory().total / 1024**3:.1f} GB"
    )  # noqa: print
    print(f"- Current CPU Usage: {psutil.cpu_percent()}%")  # noqa: print
    print()  # noqa: print

    # Initial GPU status
    gpu_before = await measure_gpu_utilization()
    if gpu_before:
        print("GPU Status (Before):")  # noqa: print
        print(f"- Utilization: {gpu_before['gpu_util']}%")  # noqa: print
        print(  # noqa: print
            f"- Memory Used: {gpu_before['memory_used']}/{gpu_before['memory_total']} MB"
        )
        print(f"- Temperature: {gpu_before['temperature']}°C")  # noqa: print
        print(f"- Power Draw: {gpu_before['power']} W")  # noqa: print
        print()  # noqa: print

    # Initialize semantic chunker
    print("Initializing Semantic Chunker...")  # noqa: print
    chunker = AutoBotSemanticChunker(
        embedding_model="all-MiniLM-L6-v2",
        percentile_threshold=95.0,
        min_chunk_size=100,
        max_chunk_size=1000,
    )

    # Test performance
    print("Starting Performance Test...")  # noqa: print
    print(f"Text Length: {len(TEST_TEXT)} characters")  # noqa: print
    print(f"Estimated Sentences: ~{len(TEST_TEXT.split('.'))} sentences")  # noqa: print
    print()  # noqa: print

    # Measure processing time
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss / 1024**2

    # Run semantic chunking
    chunks = await chunker.chunk_text(TEST_TEXT)

    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss / 1024**2

    processing_time = end_time - start_time
    memory_used = end_memory - start_memory

    # Final GPU status
    gpu_after = await measure_gpu_utilization()

    # Results
    print("=== PERFORMANCE RESULTS ===")  # noqa: print
    print(f"Processing Time: {processing_time:.2f} seconds")  # noqa: print
    print(f"Memory Usage: {memory_used:.1f} MB")  # noqa: print
    print(f"Chunks Created: {len(chunks)}")  # noqa: print
    print(  # noqa: print
        f"Average Chunk Size: {sum(len(c.content) for c in chunks) // len(chunks)} chars"
    )
    print()  # noqa: print

    if gpu_after:
        print("GPU Utilization During Processing:")  # noqa: print
        print(f"- GPU Utilization: {gpu_after['gpu_util']}%")  # noqa: print
        print(  # noqa: print
            f"- Memory Used: {gpu_after['memory_used']}/{gpu_after['memory_total']} MB"
        )
        print(f"- Temperature: {gpu_after['temperature']}°C")  # noqa: print
        print(f"- Power Draw: {gpu_after['power']} W")  # noqa: print
        print()  # noqa: print

        if gpu_before:
            util_increase = gpu_after["gpu_util"] - gpu_before["gpu_util"]
            memory_increase = gpu_after["memory_used"] - gpu_before["memory_used"]
            temp_increase = gpu_after["temperature"] - gpu_before["temperature"]

            print("GPU Usage Change:")  # noqa: print
            print(f"- Utilization: +{util_increase:.1f}%")  # noqa: print
            print(f"- Memory: +{memory_increase:.0f} MB")  # noqa: print
            print(f"- Temperature: +{temp_increase:.1f}°C")  # noqa: print
            print()  # noqa: print

    # Performance analysis
    print("=== OPTIMIZATION OPPORTUNITIES ===")  # noqa: print

    # GPU utilization analysis
    if gpu_after and gpu_after["gpu_util"] < 50:
        print(  # noqa: print
            f"⚠️ GPU underutilized ({gpu_after['gpu_util']}%) - Opportunity for optimization"
        )
        print("   - Increase batch sizes for embedding computation")  # noqa: print
        print("   - Enable mixed precision (FP16) for faster inference")  # noqa: print
        print("   - Optimize tensor operations for RTX 4070")  # noqa: print
    elif gpu_after and gpu_after["gpu_util"] > 85:
        print(f"✅ GPU well utilized ({gpu_after['gpu_util']}%)")  # noqa: print

    # Performance targets
    sentences_estimated = len(TEST_TEXT.split("."))
    sentences_per_second = sentences_estimated / processing_time

    print(  # noqa: print
        f"\nCurrent Performance: {sentences_per_second:.1f} sentences/second"
    )  # noqa: print
    print(  # noqa: print
        f"Target Performance: {sentences_per_second * 3:.1f} sentences/second (3x improvement)"
    )

    # Memory efficiency
    if gpu_after:
        memory_util = gpu_after["memory_used"] / gpu_after["memory_total"] * 100
        print(f"GPU Memory Utilization: {memory_util:.1f}%")  # noqa: print
        if memory_util < 30:
            print(  # noqa: print
                "   - GPU memory underutilized, can handle larger batches"
            )  # noqa: print
        elif memory_util > 85:
            print("   - GPU memory highly utilized, good efficiency")  # noqa: print

    # CPU utilization
    final_cpu = psutil.cpu_percent()
    print(f"CPU Utilization: {final_cpu}%")  # noqa: print
    if final_cpu < 20:
        print(  # noqa: print
            "   - CPU underutilized, opportunity for parallel processing"
        )  # noqa: print

    return {
        "processing_time": processing_time,
        "memory_used": memory_used,
        "chunks_created": len(chunks),
        "gpu_util": gpu_after["gpu_util"] if gpu_after else 0,
        "sentences_per_second": sentences_per_second,
    }


async def npu_assessment():
    """Assess NPU worker functionality."""
    print("\n=== NPU WORKER ASSESSMENT ===")  # noqa: print

    try:
        import asyncio

        import aiohttp

        async with aiohttp.ClientSession() as session:
            # Test NPU worker health
            try:
                async with session.get(
                    "http://172.16.168.22:8081/health", timeout=5
                ) as resp:
                    health_data = await resp.json()
                    print(  # noqa: print
                        f"NPU Worker Status: {health_data.get('status', 'unknown')}"
                    )  # noqa: print
                    print(  # noqa: print
                        f"Device: {health_data.get('device', 'unknown')}"
                    )  # noqa: print
                    print(  # noqa: print
                        f"Models Loaded: {health_data.get('models_loaded', 0)}"
                    )  # noqa: print
                    print(  # noqa: print
                        f"Requests Processed: {health_data.get('requests_processed', 0)}"
                    )

                    if health_data.get("device") == "CPU":
                        print(  # noqa: print
                            "⚠️ NPU Worker running on CPU - No Intel NPU acceleration detected"
                        )
                        return False
                    else:
                        print(  # noqa: print
                            "✅ NPU Worker potentially using hardware acceleration"
                        )  # noqa: print
                        return True

            except asyncio.TimeoutError:
                print("❌ NPU Worker not responding (timeout)")  # noqa: print
                return False
            except Exception as e:
                print(f"❌ NPU Worker error: {e}")  # noqa: print
                return False

    except ImportError:
        print("❌ aiohttp not available for NPU testing")  # noqa: print
        return False


if __name__ == "__main__":

    async def main():
        # Run performance test
        results = await performance_test()

        # Assess NPU
        npu_available = await npu_assessment()

        # Optimization recommendations
        print("\n=== OPTIMIZATION RECOMMENDATIONS ===")  # noqa: print

        if results["gpu_util"] < 50:
            print("🚀 HIGH PRIORITY: GPU Optimization")  # noqa: print
            print(  # noqa: print
                "   1. Increase embedding batch sizes (current: adaptive)"
            )  # noqa: print
            print("   2. Enable FP16 mixed precision")  # noqa: print
            print("   3. Optimize GPU memory pooling")  # noqa: print
            print("   4. Target: 70-85% GPU utilization")  # noqa: print

        if results["sentences_per_second"] < 50:
            print("⚡ MEDIUM PRIORITY: Processing Speed")  # noqa: print
            print("   1. Optimize sentence splitting algorithm")  # noqa: print
            print("   2. Implement parallel embedding computation")  # noqa: print
            print("   3. Cache embeddings for repeated content")  # noqa: print

        if not npu_available:
            print("🔧 MEDIUM PRIORITY: NPU Integration")  # noqa: print
            print("   1. Investigate Intel NPU hardware availability")  # noqa: print
            print("   2. If NPU not functional, consolidate to GPU-only")  # noqa: print
            print("   3. Optimize workload distribution")  # noqa: print

        # Expected improvements
        print("\n=== EXPECTED IMPROVEMENTS ===")  # noqa: print
        print("With optimizations:")  # noqa: print
        print(  # noqa: print
            f"- Processing Speed: {results['processing_time']:.2f}s → {results['processing_time']/3:.2f}s (3x faster)"
        )
        print(  # noqa: print
            f"- GPU Utilization: {results['gpu_util']:.0f}% → 75% (optimal)"
        )  # noqa: print
        print(  # noqa: print
            f"- Throughput: {results['sentences_per_second']:.1f} → {results['sentences_per_second']*3:.1f} sentences/sec"
        )

        return results

    asyncio.run(main())
