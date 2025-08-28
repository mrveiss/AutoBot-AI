#!/usr/bin/env python3
"""
Startup Performance Profiler
Profiles AutoBot backend startup to identify bottlenecks
"""
import cProfile
import pstats
import time
import sys
import os

def profile_startup():
    """Profile the startup sequence"""
    print("🔍 Starting backend startup profiling...")
    
    # Add the project root to Python path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    start_time = time.time()
    
    try:
        # Import main components
        print("Importing main modules...")
        from backend import main, app_factory
        
        print("Creating FastAPI app...")
        app = app_factory.create_app()
        
        end_time = time.time()
        
    except Exception as e:
        print(f"Error during profiling: {e}")
        return
    finally:
        profiler.disable()
    
    print(f"Startup completed in {end_time - start_time:.3f} seconds")
    
    # Save and display results
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    
    print("\n🔝 Top 10 slowest functions:")
    stats.print_stats(10)
    
    # Save detailed report
    with open('startup_profile.txt', 'w') as f:
        stats.print_stats(file=f)
    
    print("\nDetailed profile saved to startup_profile.txt")

if __name__ == "__main__":
    profile_startup()
