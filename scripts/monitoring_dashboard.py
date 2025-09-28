#!/usr/bin/env python3
"""
AutoBot Monitoring Dashboard
Provides quick status overview and health metrics for the codebase
"""

import json
import os
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AutoBotMonitor:
    """Monitoring dashboard for AutoBot system health"""
    
    def __init__(self):
        self.project_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
    def get_system_overview(self):
        """Get high-level system status"""
        print("🤖 AUTOBOT SYSTEM MONITORING DASHBOARD")
        print("=" * 60)
        print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📁 Project Root: {self.project_root}")
        print()
        
    def check_recent_analysis(self):
        """Check for recent profiling analysis"""
        print("📊 RECENT ANALYSIS STATUS")
        print("-" * 30)
        
        analysis_files = list(self.project_root.glob("reports/codebase_analysis_*.json"))
        
        if analysis_files:
            latest_analysis = max(analysis_files, key=os.path.getctime)
            age = datetime.now() - datetime.fromtimestamp(os.path.getctime(latest_analysis))
            
            if age < timedelta(days=1):
                status = "🟢 FRESH"
            elif age < timedelta(days=7):
                status = "🟡 RECENT"  
            else:
                status = "🔴 STALE"
                
            print(f"Latest Analysis: {latest_analysis.name}")
            print(f"Age: {age.days} days, {age.seconds // 3600} hours")
            print(f"Status: {status}")
            
            # Load and display key metrics
            try:
                with open(latest_analysis) as f:
                    data = json.load(f)
                
                static = data.get("static_analysis", {})
                hotspots = data.get("performance_hotspots", {})
                
                print(f"Functions Analyzed: {len(static.get('function_definitions', {}))}")
                print(f"High Complexity: {len(hotspots.get('high_complexity_functions', []))}")
                print(f"Duplicates: {len(hotspots.get('duplicate_code', []))}")
                print(f"Recommendations: {len(data.get('recommendations', []))}")
                
            except Exception as e:
                print(f"❌ Could not read analysis data: {e}")
        else:
            print("❌ No analysis files found")
            print("🔧 Run: python scripts/comprehensive_code_profiler.py")
        
        print()
        
    def check_api_performance(self):
        """Quick API performance check"""
        print("🌐 API PERFORMANCE STATUS")
        print("-" * 30)
        
        try:
            result = subprocess.run([
                sys.executable, "scripts/profile_api_endpoints.py"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Parse results for quick summary
                lines = result.stdout.split('\n')
                fast_endpoints = len([l for l in lines if '🚀 FAST' in l])
                good_endpoints = len([l for l in lines if '⚡ GOOD' in l])
                slow_endpoints = len([l for l in lines if '⚠️  SLOW' in l or '🐌 VERY SLOW' in l])
                
                print(f"🚀 Fast Endpoints: {fast_endpoints}")
                print(f"⚡ Good Endpoints: {good_endpoints}")
                print(f"🐌 Slow Endpoints: {slow_endpoints}")
                
                if slow_endpoints > 0:
                    print("❌ Some endpoints need optimization")
                else:
                    print("✅ All endpoints performing well")
            else:
                print("⚠️ Backend not running - cannot test APIs")
                
        except subprocess.TimeoutExpired:
            print("⏰ API test timeout - backend may be slow")
        except Exception as e:
            print(f"❌ API test error: {e}")
            
        print()
        
    def check_security_status(self):
        """Check security systems status"""
        print("🔒 SECURITY STATUS")
        print("-" * 30)
        
        security_checks = [
            ("Command Validator", "src/security/command_validator.py"),
            ("Allowed Commands Config", "config/allowed_commands.json"),
            ("File Upload Security", "backend/api/files.py"),
        ]
        
        all_secure = True
        for name, path in security_checks:
            if Path(path).exists():
                print(f"✅ {name}: Present")
            else:
                print(f"❌ {name}: Missing")
                all_secure = False
        
        # Test command validator if available
        try:
            from src.security.command_validator import get_command_validator
from src.constants import NetworkConstants, ServiceURLs
            validator = get_command_validator()
            
            # Quick functionality test
            safe_test = validator.validate_command_request("show system info")
            danger_test = validator.validate_command_request("run rm -rf /")
            
            if (safe_test and safe_test.get("type") == "system_info" and 
                danger_test and danger_test.get("type") == "blocked"):
                print("✅ Command Validator: Functional")
            else:
                print("❌ Command Validator: Issues detected")
                all_secure = False
                
        except Exception as e:
            print(f"⚠️ Command Validator: Cannot test ({e})")
            
        if all_secure:
            print("🛡️ Overall Security: GOOD")
        else:
            print("🔴 Overall Security: NEEDS ATTENTION")
            
        print()
        
    def check_testing_capabilities(self):
        """Check testing infrastructure status"""
        print("🧪 TESTING INFRASTRUCTURE")
        print("-" * 30)
        
        test_scripts = [
            ("Codebase Profiler", "scripts/comprehensive_code_profiler.py"),
            ("Automated Testing", "scripts/automated_testing_procedure.py"),
            ("API Performance", "scripts/profile_api_endpoints.py"),
            ("Backend Profiler", "scripts/profile_backend.py"),
        ]
        
        available_tests = 0
        for name, path in test_scripts:
            if Path(path).exists():
                print(f"✅ {name}: Available")
                available_tests += 1
            else:
                print(f"❌ {name}: Missing")
        
        print(f"📊 Test Coverage: {available_tests}/{len(test_scripts)} ({available_tests/len(test_scripts)*100:.0f}%)")
        
        if available_tests == len(test_scripts):
            print("🎯 Testing Infrastructure: COMPLETE")
        else:
            print("⚠️ Testing Infrastructure: INCOMPLETE")
            
        print()
        
    def provide_recommendations(self):
        """Provide actionable recommendations"""
        print("💡 RECOMMENDATIONS")
        print("-" * 30)
        
        # Check if analysis is recent
        analysis_files = list(self.project_root.glob("reports/codebase_analysis_*.json"))
        if not analysis_files:
            print("🔧 Run codebase profiling: python scripts/comprehensive_code_profiler.py")
        else:
            latest = max(analysis_files, key=os.path.getctime)
            age = datetime.now() - datetime.fromtimestamp(os.path.getctime(latest))
            if age > timedelta(days=7):
                print("🔄 Update profiling analysis (>7 days old)")
        
        # Check for common issues
        try:
            # Check if backend is running
            result = subprocess.run([
                "curl", "-s", "ServiceURLs.BACKEND_LOCAL/api/system/health"
            ], capture_output=True, timeout=5)
            
            if result.returncode != 0:
                print("🚀 Start backend for full monitoring: ./run_agent.sh --test-mode")
        except:
            print("🚀 Start backend for API testing: ./run_agent.sh --test-mode")
            
        # Check for required tools
        tools = ["flake8", "pytest"]
        for tool in tools:
            try:
                subprocess.run([tool, "--version"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"📦 Install {tool}: pip install {tool}")
        
        print("📋 Regular maintenance: Run weekly profiling and testing")
        print("🎯 Focus areas: Check optimization_roadmap.md for priorities")
        print()
        
    def run_dashboard(self):
        """Run complete monitoring dashboard"""
        self.get_system_overview()
        self.check_recent_analysis()
        self.check_api_performance()
        self.check_security_status()
        self.check_testing_capabilities()
        self.provide_recommendations()
        
        print("🎉 MONITORING COMPLETE")
        print("=" * 60)
        print("For detailed analysis, run:")
        print("  python scripts/comprehensive_code_profiler.py")
        print("  python scripts/automated_testing_procedure.py")
        print("  python scripts/profile_api_endpoints.py")

def main():
    """Main monitoring execution"""
    monitor = AutoBotMonitor()
    monitor.run_dashboard()

if __name__ == "__main__":
    main()