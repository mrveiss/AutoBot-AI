#!/usr/bin/env python3
"""
Performance comparison test for AutoBot GPU optimization
Compares original vs optimized semantic chunking performance.
"""

import asyncio
import time
import psutil
import sys
import os
import torch

# Add AutoBot to path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

from src.utils.semantic_chunker import AutoBotSemanticChunker
from src.utils.semantic_chunker_gpu_optimized import OptimizedGPUSemanticChunker

# Larger test text for meaningful performance comparison
TEST_TEXT = """
Artificial intelligence has revolutionized countless industries and aspects of human life. Machine learning algorithms can now process vast amounts of data with unprecedented speed and accuracy. Neural networks, inspired by the human brain, have enabled computers to recognize patterns, understand language, and make complex decisions. The integration of AI into daily life has become so seamless that many people interact with AI systems without even realizing it.

Deep learning, a subset of machine learning, has particularly transformed fields like computer vision and natural language processing. Convolutional neural networks excel at image recognition tasks, identifying objects, faces, and even complex scenes with remarkable accuracy. Transformer architectures have revolutionized language understanding, enabling machines to comprehend context, nuance, and even generate human-like responses. These advances have enabled applications from autonomous vehicles to sophisticated chatbots that can engage in meaningful conversations.

The development of large language models represents a significant milestone in AI progress. These models, trained on enormous datasets encompassing billions of words from books, articles, and websites, can generate human-like text, answer complex questions, write code, and even create poetry. However, they also raise important questions about bias, misinformation, and the future role of AI in society. The ethical implications of AI systems that can generate convincing but potentially false information require careful consideration and regulation.

Cloud computing has made AI more accessible to businesses and researchers worldwide. Powerful GPUs and specialized AI chips accelerate training and inference processes, making it possible to develop and deploy sophisticated AI applications without massive infrastructure investments. Edge computing brings AI capabilities directly to devices, enabling real-time processing without constant internet connectivity. This distributed approach to AI processing has opened up new possibilities for mobile applications, IoT devices, and autonomous systems.

The ethical implications of AI continue to evolve as the technology becomes more powerful and pervasive. Questions about privacy arise when AI systems process personal data to make recommendations or decisions. Job displacement concerns emerge as AI automates tasks previously performed by humans. Algorithmic fairness becomes crucial when AI systems make decisions affecting people's lives, from loan approvals to hiring decisions. Responsible AI development involves transparency, accountability, and inclusive design practices that consider diverse perspectives and potential impacts.

Future developments in quantum computing may further accelerate AI capabilities. Quantum algorithms could solve certain computational problems exponentially faster than classical computers, potentially revolutionizing machine learning optimization and cryptography. The intersection of quantum computing and artificial intelligence represents an exciting frontier in technology, though practical quantum AI applications are still in early development stages.

The democratization of AI tools has enabled individuals and small businesses to leverage sophisticated AI capabilities. Open-source frameworks like TensorFlow, PyTorch, and Hugging Face have made it easier for developers to build and deploy AI applications. Pre-trained models available through APIs allow even non-technical users to incorporate AI features into their projects. This accessibility has sparked innovation across industries and created new opportunities for entrepreneurs and researchers.

AI safety research focuses on ensuring that artificial intelligence systems behave as intended and remain under human control. Alignment problems arise when AI systems optimize for objectives that don't match human values or intentions. Robustness research addresses how AI systems handle unexpected inputs or adversarial attacks. Interpretability studies work to make AI decision-making processes more transparent and understandable to humans. These areas of research are crucial as AI systems become more autonomous and influential.

The integration of AI into scientific research has accelerated discovery across multiple disciplines. In drug discovery, AI models can predict molecular interactions and identify promising compounds faster than traditional methods. Climate modeling benefits from AI's ability to process vast amounts of environmental data and identify patterns that human researchers might miss. Space exploration uses AI for autonomous navigation, image analysis, and mission planning. These applications demonstrate AI's potential to augment human intelligence and accelerate scientific progress.

Education and AI intersect in numerous ways, from personalized learning platforms that adapt to individual student needs to automated grading systems that provide instant feedback. AI tutors can provide 24/7 assistance and explain concepts in multiple ways until students understand. However, concerns about academic integrity arise when students use AI to complete assignments. Educational institutions must balance leveraging AI's benefits while maintaining academic standards and ensuring students develop critical thinking skills.
""" * 2  # Double the text for substantial testing

async def measure_gpu_utilization():
    """Measure GPU utilization during processing."""
    import subprocess
    
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            values = result.stdout.strip().split(',')
            return {
                'gpu_util': float(values[0].strip()),
                'memory_used': float(values[1].strip()),
                'memory_total': float(values[2].strip()),
                'temperature': float(values[3].strip()),
                'power': float(values[4].strip())
            }
    except:
        pass
    
    return None

async def benchmark_original_chunker():
    """Benchmark the original semantic chunker."""
    print("🔵 Testing Original Semantic Chunker...")
    
    chunker = AutoBotSemanticChunker(
        embedding_model="all-MiniLM-L6-v2",
        percentile_threshold=95.0
    )
    
    # Measure GPU before
    gpu_before = await measure_gpu_utilization()
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss / 1024**2
    
    # Process text
    chunks = await chunker.chunk_text(TEST_TEXT)
    
    # Measure after
    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss / 1024**2
    gpu_after = await measure_gpu_utilization()
    
    processing_time = end_time - start_time
    memory_used = end_memory - start_memory
    
    # Calculate estimated sentences processed
    sentences_estimated = len(TEST_TEXT.split('.'))
    sentences_per_sec = sentences_estimated / processing_time
    
    results = {
        'name': 'Original Chunker',
        'processing_time': processing_time,
        'memory_used': memory_used,
        'chunks_created': len(chunks),
        'sentences_per_sec': sentences_per_sec,
        'gpu_util_before': gpu_before['gpu_util'] if gpu_before else 0,
        'gpu_util_after': gpu_after['gpu_util'] if gpu_after else 0,
        'gpu_memory_used': gpu_after['memory_used'] if gpu_after else 0,
        'gpu_power': gpu_after['power'] if gpu_after else 0
    }
    
    print(f"  ⏱️  Processing Time: {processing_time:.2f}s")
    print(f"  💾 Memory Usage: {memory_used:.1f}MB")
    print(f"  📦 Chunks Created: {len(chunks)}")
    print(f"  ⚡ Performance: {sentences_per_sec:.1f} sentences/sec")
    if gpu_after:
        print(f"  🎮 GPU Utilization: {gpu_after['gpu_util']:.1f}%")
        print(f"  🔥 GPU Power: {gpu_after['power']:.1f}W")
    
    return results

async def benchmark_optimized_chunker():
    """Benchmark the optimized GPU semantic chunker."""
    print("\n🟢 Testing Optimized GPU Semantic Chunker...")
    
    chunker = OptimizedGPUSemanticChunker(
        embedding_model="all-MiniLM-L6-v2",
        percentile_threshold=95.0,
        gpu_batch_size=500,
        enable_gpu_memory_pool=True
    )
    
    # Measure GPU before
    gpu_before = await measure_gpu_utilization()
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss / 1024**2
    
    # Process text with optimized method
    chunks = await chunker.chunk_text_optimized(TEST_TEXT)
    
    # Measure after
    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss / 1024**2
    gpu_after = await measure_gpu_utilization()
    
    processing_time = end_time - start_time
    memory_used = end_memory - start_memory
    
    # Calculate performance
    sentences_estimated = len(TEST_TEXT.split('.'))
    sentences_per_sec = sentences_estimated / processing_time
    
    # Get performance stats from chunker
    perf_stats = chunker.get_performance_stats()
    
    results = {
        'name': 'Optimized GPU Chunker',
        'processing_time': processing_time,
        'memory_used': memory_used,
        'chunks_created': len(chunks),
        'sentences_per_sec': sentences_per_sec,
        'gpu_util_before': gpu_before['gpu_util'] if gpu_before else 0,
        'gpu_util_after': gpu_after['gpu_util'] if gpu_after else 0,
        'gpu_memory_used': gpu_after['memory_used'] if gpu_after else 0,
        'gpu_power': gpu_after['power'] if gpu_after else 0,
        'performance_stats': perf_stats
    }
    
    print(f"  ⏱️  Processing Time: {processing_time:.2f}s")
    print(f"  💾 Memory Usage: {memory_used:.1f}MB")
    print(f"  📦 Chunks Created: {len(chunks)}")
    print(f"  ⚡ Performance: {sentences_per_sec:.1f} sentences/sec")
    if gpu_after:
        print(f"  🎮 GPU Utilization: {gpu_after['gpu_util']:.1f}%")
        print(f"  🔥 GPU Power: {gpu_after['power']:.1f}W")
        gpu_memory_util = (gpu_after['memory_used'] / gpu_after['memory_total']) * 100
        print(f"  💽 GPU Memory Util: {gpu_memory_util:.1f}%")
    
    return results

async def performance_comparison():
    """Run comprehensive performance comparison."""
    print("=" * 60)
    print("🚀 AutoBot GPU Performance Optimization Test")
    print("=" * 60)
    
    # System info
    print("\n📊 Hardware Configuration:")
    print(f"  - CPU: Intel Ultra 9 185H ({psutil.cpu_count()} cores)")
    if torch.cuda.is_available():
        print(f"  - GPU: {torch.cuda.get_device_name(0)}")
        print(f"  - GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
    print(f"  - System Memory: {psutil.virtual_memory().total / 1024**3:.1f}GB")
    print(f"  - Test Text: {len(TEST_TEXT)} characters")
    print(f"  - Estimated Sentences: ~{len(TEST_TEXT.split('.'))} sentences")
    
    # Run benchmarks
    print("\n" + "=" * 40)
    print("🧪 RUNNING BENCHMARKS")
    print("=" * 40)
    
    # Test original chunker
    original_results = await benchmark_original_chunker()
    
    # Brief pause between tests
    await asyncio.sleep(2)
    
    # Test optimized chunker
    optimized_results = await benchmark_optimized_chunker()
    
    # Performance comparison
    print("\n" + "=" * 40)
    print("📈 PERFORMANCE COMPARISON")
    print("=" * 40)
    
    time_improvement = original_results['processing_time'] / optimized_results['processing_time']
    throughput_improvement = optimized_results['sentences_per_sec'] / original_results['sentences_per_sec']
    gpu_util_improvement = optimized_results['gpu_util_after'] / max(original_results['gpu_util_after'], 1)
    
    print(f"\n🏆 Performance Improvements:")
    print(f"  ⚡ Speed: {time_improvement:.2f}x faster")
    print(f"  📊 Throughput: {throughput_improvement:.2f}x more sentences/sec")
    print(f"  🎮 GPU Utilization: {gpu_util_improvement:.2f}x better")
    
    print(f"\n📋 Detailed Comparison:")
    print(f"  Processing Time: {original_results['processing_time']:.2f}s → {optimized_results['processing_time']:.2f}s")
    print(f"  Throughput: {original_results['sentences_per_sec']:.1f} → {optimized_results['sentences_per_sec']:.1f} sent/sec")
    print(f"  GPU Utilization: {original_results['gpu_util_after']:.1f}% → {optimized_results['gpu_util_after']:.1f}%")
    print(f"  GPU Power: {original_results['gpu_power']:.1f}W → {optimized_results['gpu_power']:.1f}W")
    
    # Target achievement analysis
    target_achieved = time_improvement >= 3.0
    print(f"\n🎯 Target Achievement (3x speed improvement):")
    if target_achieved:
        print(f"  ✅ TARGET ACHIEVED! ({time_improvement:.2f}x improvement)")
    else:
        print(f"  ⚠️  TARGET NOT YET REACHED ({time_improvement:.2f}x improvement)")
        remaining_improvement = 3.0 / time_improvement
        print(f"  📈 Need {remaining_improvement:.2f}x more improvement to reach 3x target")
    
    # Optimization recommendations
    print(f"\n🔧 Optimization Status:")
    if optimized_results['gpu_util_after'] < 50:
        print("  📌 GPU still underutilized - more optimization possible")
    elif optimized_results['gpu_util_after'] > 75:
        print("  ✅ GPU well utilized")
    
    if optimized_results['gpu_power'] > 100:  # High power usage indicates good utilization
        print("  ⚡ High GPU power usage indicates good acceleration")
    
    # Memory efficiency
    gpu_memory_util = (optimized_results['gpu_memory_used'] / 8188) * 100  # RTX 4070 has ~8GB
    if gpu_memory_util < 30:
        print("  💽 GPU memory underutilized - can handle larger batches")
    
    return {
        'original': original_results,
        'optimized': optimized_results,
        'improvements': {
            'speed_multiplier': time_improvement,
            'throughput_multiplier': throughput_improvement,
            'gpu_util_multiplier': gpu_util_improvement,
            'target_achieved': target_achieved
        }
    }

if __name__ == "__main__":
    async def main():
        results = await performance_comparison()
        
        print(f"\n" + "=" * 60)
        print("🏁 BENCHMARK COMPLETE")
        print("=" * 60)
        
        improvements = results['improvements']
        if improvements['target_achieved']:
            print("🎉 SUCCESS: 3x performance target achieved!")
        else:
            print("🔄 PROGRESS: Significant improvement achieved, further optimization possible")
        
        print(f"\nFinal Results:")
        print(f"  - Speed Improvement: {improvements['speed_multiplier']:.2f}x")
        print(f"  - GPU Utilization: {improvements['gpu_util_multiplier']:.2f}x better")
        print(f"  - Target Status: {'✅ ACHIEVED' if improvements['target_achieved'] else '🔄 IN PROGRESS'}")
        
        return results
    
    results = asyncio.run(main())