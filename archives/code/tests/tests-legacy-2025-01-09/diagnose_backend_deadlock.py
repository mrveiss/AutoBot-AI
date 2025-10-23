#!/usr/bin/env python3
"""
Backend Deadlock Diagnostic Tool for AutoBot
Identifies blocking operations causing high CPU usage and timeouts
"""

import os
import sys
import time
import psutil
import signal
import threading
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

class BackendDiagnostic:
    """Diagnostic tool for backend deadlock issues"""
    
    def __init__(self):
        self.backend_processes = []
        self.monitoring = False
        
    def find_backend_processes(self) -> List[psutil.Process]:
        """Find all AutoBot backend processes"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if ('uvicorn' in cmdline and 'backend' in cmdline) or \
                   ('python' in cmdline and 'backend' in cmdline):
                    processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return processes
    
    def analyze_cpu_usage(self) -> Dict:
        """Analyze CPU usage patterns"""
        processes = self.find_backend_processes()
        
        if not processes:
            return {"error": "No backend processes found"}
        
        analysis = {
            "processes": [],
            "high_cpu_detected": False,
            "recommendations": []
        }
        
        for proc in processes:
            try:
                cpu_percent = proc.cpu_percent(interval=1)
                memory_info = proc.memory_info()
                
                proc_info = {
                    "pid": proc.pid,
                    "cpu_percent": cpu_percent,
                    "memory_mb": memory_info.rss / 1024 / 1024,
                    "cmdline": ' '.join(proc.cmdline()),
                    "status": proc.status(),
                    "num_threads": proc.num_threads()
                }
                
                analysis["processes"].append(proc_info)
                
                if cpu_percent > 50:
                    analysis["high_cpu_detected"] = True
                    analysis["recommendations"].append(
                        f"Process {proc.pid} shows high CPU usage ({cpu_percent:.1f}%) - indicates blocking operations"
                    )
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                analysis["processes"].append({
                    "pid": proc.pid if hasattr(proc, 'pid') else 'unknown',
                    "error": str(e)
                })
        
        return analysis
    
    def check_potential_deadlock_causes(self) -> Dict:
        """Check for known deadlock causes from documentation"""
        causes = {
            "sync_file_io": self._check_sync_file_io(),
            "redis_connections": self._check_redis_connections(),
            "llm_timeouts": self._check_llm_timeouts(),
            "knowledge_base_blocking": self._check_kb_blocking(),
            "memory_leaks": self._check_memory_patterns()
        }
        
        return causes
    
    def _check_sync_file_io(self) -> Dict:
        """Check for synchronous file I/O operations"""
        # Look for files that should use asyncio.to_thread
        sync_io_files = [
            "src/agents/kb_librarian_agent.py",
            "src/knowledge_base.py", 
            "src/chat_workflow_manager.py"
        ]
        
        findings = []
        for file_path in sync_io_files:
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                        if 'open(' in content and 'asyncio.to_thread' not in content:
                            findings.append(f"{file_path}: Contains sync file operations without async wrapper")
                        elif 'asyncio.to_thread' in content:
                            findings.append(f"{file_path}: ✅ Uses async file operations")
                except Exception as e:
                    findings.append(f"{file_path}: Error reading - {e}")
        
        return {
            "status": "good" if all("✅" in f for f in findings) else "needs_fix",
            "findings": findings
        }
    
    def _check_redis_connections(self) -> Dict:
        """Check Redis connection configuration"""
        redis_files = [
            "src/utils/redis_database_manager.py",
            "backend/fast_app_factory_fix.py"
        ]
        
        findings = []
        for file_path in redis_files:
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                        if 'timeout=2' in content or 'socket_timeout=2' in content:
                            findings.append(f"{file_path}: ✅ Has timeout protection")
                        elif 'timeout=' in content:
                            findings.append(f"{file_path}: Has timeout but may not be 2 seconds")
                        else:
                            findings.append(f"{file_path}: No timeout protection found")
                except Exception as e:
                    findings.append(f"{file_path}: Error reading - {e}")
        
        return {
            "status": "good" if all("✅" in f for f in findings) else "needs_check",
            "findings": findings
        }
    
    def _check_llm_timeouts(self) -> Dict:
        """Check LLM timeout configurations"""
        llm_files = [
            "src/llm_interface.py",
            "src/async_llm_interface.py"
        ]
        
        findings = []
        for file_path in llm_files:
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                        if 'timeout=600' in content or 'timeout: int = 600' in content:
                            findings.append(f"{file_path}: ❌ Has 600 second timeout (too long)")
                        elif 'timeout=30' in content or 'timeout: int = 30' in content:
                            findings.append(f"{file_path}: ✅ Has 30 second timeout")
                        else:
                            findings.append(f"{file_path}: Timeout configuration unclear")
                except Exception as e:
                    findings.append(f"{file_path}: Error reading - {e}")
        
        return {
            "status": "good" if all("✅" in f for f in findings) else "needs_fix", 
            "findings": findings
        }
    
    def _check_kb_blocking(self) -> Dict:
        """Check knowledge base blocking operations"""
        kb_files = [
            "src/knowledge_base.py",
            "src/chat_workflow_manager.py"
        ]
        
        findings = []
        for file_path in kb_files:
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                        if 'llama_index' in content and 'asyncio.to_thread' in content:
                            findings.append(f"{file_path}: ✅ Uses async wrapper for llama_index")
                        elif 'llama_index' in content:
                            findings.append(f"{file_path}: ❌ Uses llama_index without async wrapper")
                        else:
                            findings.append(f"{file_path}: No llama_index usage found")
                except Exception as e:
                    findings.append(f"{file_path}: Error reading - {e}")
        
        return {
            "status": "good" if all("✅" in f for f in findings) else "needs_fix",
            "findings": findings
        }
    
    def _check_memory_patterns(self) -> Dict:
        """Check for memory leak patterns"""
        processes = self.find_backend_processes()
        
        if not processes:
            return {"status": "no_processes", "findings": ["No backend processes to analyze"]}
        
        findings = []
        for proc in processes:
            try:
                memory_mb = proc.memory_info().rss / 1024 / 1024
                if memory_mb > 1000:  # > 1GB
                    findings.append(f"Process {proc.pid}: High memory usage ({memory_mb:.1f}MB)")
                else:
                    findings.append(f"Process {proc.pid}: Normal memory usage ({memory_mb:.1f}MB)")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                findings.append(f"Process {proc.pid}: Could not read memory info")
        
        return {
            "status": "good" if all("Normal" in f for f in findings) else "needs_check",
            "findings": findings
        }
    
    def generate_diagnostic_report(self) -> str:
        """Generate comprehensive diagnostic report"""
        print("🔍 AutoBot Backend Deadlock Diagnostic")
        print("=" * 60)
        
        # Check CPU usage
        print("\n📊 CPU Usage Analysis:")
        cpu_analysis = self.analyze_cpu_usage()
        
        if "error" in cpu_analysis:
            print(f"   ❌ {cpu_analysis['error']}")
        else:
            for proc_info in cpu_analysis["processes"]:
                if "error" in proc_info:
                    print(f"   ❌ Process {proc_info['pid']}: {proc_info['error']}")
                else:
                    cpu_icon = "🔥" if proc_info["cpu_percent"] > 50 else "✅"
                    print(f"   {cpu_icon} PID {proc_info['pid']}: {proc_info['cpu_percent']:.1f}% CPU, {proc_info['memory_mb']:.1f}MB RAM")
            
            if cpu_analysis["high_cpu_detected"]:
                print("\n   🚨 HIGH CPU USAGE DETECTED - Backend likely deadlocked")
                for rec in cpu_analysis["recommendations"]:
                    print(f"   → {rec}")
        
        # Check potential deadlock causes
        print("\n🔧 Deadlock Cause Analysis:")
        causes = self.check_potential_deadlock_causes()
        
        for cause_name, cause_data in causes.items():
            status_icon = "✅" if cause_data["status"] == "good" else "⚠️" if cause_data["status"] == "needs_check" else "❌"
            print(f"\n   {status_icon} {cause_name.replace('_', ' ').title()}:")
            
            for finding in cause_data["findings"]:
                if "✅" in finding:
                    print(f"      ✅ {finding}")
                elif "❌" in finding:
                    print(f"      ❌ {finding}")
                else:
                    print(f"      • {finding}")
        
        # Generate recommendations
        print(f"\n🎯 RECOMMENDATIONS:")
        recommendations = []
        
        if cpu_analysis.get("high_cpu_detected"):
            recommendations.append("URGENT: Kill backend process and restart with fixes")
        
        if causes["sync_file_io"]["status"] != "good":
            recommendations.append("Apply async file I/O fixes as documented in CLAUDE.md")
        
        if causes["llm_timeouts"]["status"] != "good":
            recommendations.append("Reduce LLM timeouts from 600s to 30s")
            
        if causes["redis_connections"]["status"] != "good":
            recommendations.append("Implement Redis timeout protection")
        
        if causes["knowledge_base_blocking"]["status"] != "good":
            recommendations.append("Wrap llama_index calls with asyncio.to_thread()")
        
        if not recommendations:
            recommendations.append("All known fixes appear to be applied - investigate other causes")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
        
        print("\n" + "=" * 60)
        
        return "diagnostic_complete"

def main():
    """Run backend diagnostic"""
    diagnostic = BackendDiagnostic()
    diagnostic.generate_diagnostic_report()

if __name__ == "__main__":
    main()