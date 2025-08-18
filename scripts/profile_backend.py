#!/usr/bin/env python3
"""
Backend Performance Profiler
Profiles every function call and execution time during startup and runtime
"""

import cProfile
import pstats
import io
import time
import sys
import os
from pstats import SortKey

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def profile_backend_startup():
    """Profile the backend startup process"""
    print("🔍 Starting comprehensive backend profiling...")
    
    # Create profiler
    profiler = cProfile.Profile()
    
    # Start profiling
    profiler.enable()
    
    try:
        # Import and create the app (this triggers all the blocking operations)
        from backend.app_factory import create_app
        print("📊 Profiling app creation...")
        app = create_app()
        print("✅ App created successfully")
        
    except Exception as e:
        print(f"❌ Error during profiling: {e}")
    finally:
        # Stop profiling
        profiler.disable()
    
    # Create stats
    stats_stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stats_stream)
    
    # Sort by cumulative time (shows what takes longest overall)
    stats.sort_stats(SortKey.CUMULATIVE)
    
    # Print top 50 slowest functions
    print("\n" + "="*80)
    print("TOP 50 SLOWEST FUNCTIONS (by cumulative time)")
    print("="*80)
    stats.print_stats(50)
    
    # Print functions taking more than 0.1 seconds
    print("\n" + "="*80)
    print("FUNCTIONS TAKING > 0.1 SECONDS")
    print("="*80)
    stats.print_stats(0.1)
    
    # Save detailed profile for snakeviz
    profile_file = "/tmp/backend_profile.prof"
    profiler.dump_stats(profile_file)
    print(f"\n📁 Detailed profile saved to: {profile_file}")
    print(f"🐍 View with: pip install snakeviz && snakeviz {profile_file}")
    
    # Print stats to string for analysis
    stats_output = stats_stream.getvalue()
    
    # Save stats to file
    with open("/tmp/backend_profile.txt", "w") as f:
        f.write(stats_output)
    print("📄 Text stats saved to: /tmp/backend_profile.txt")
    
    return stats_output

if __name__ == "__main__":
    profile_backend_startup()