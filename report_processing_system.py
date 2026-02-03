#!/usr/bin/env python3
"""
AutoBot Report Processing & Archival System
Coordinated multi-agent parallel processing with error analysis and archival
"""

import os
import json
import shutil
import asyncio
import logging
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler(
            f"/home/kali/Desktop/AutoBot/report_processing_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ReportProcessor")

@dataclass
class ReportFile:
    """Report file metadata"""
    path: str
    type: str  # 'json', 'md', 'html', 'log', 'py'
    size: int
    modified: float
    errors: List[str]
    warnings: List[str]
    status: str  # 'processed', 'archived', 'error', 'pending'
    agent_id: str = ""

@dataclass
class ProcessingResult:
    """Processing result for a report"""
    file_path: str
    success: bool
    errors_found: List[str]
    warnings_found: List[str]
    archive_path: str = ""
    processing_time: float = 0.0
    agent_id: str = ""

class ReportDiscoveryAgent:
    """Agent 1: Document Discovery Specialist"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.agent_id = "DISCOVERY_AGENT_001"
        self.logger = logging.getLogger(f"Agent.{self.agent_id}")
        self.report_files: List[ReportFile] = []
        
    def discover_reports(self) -> Dict[str, List[ReportFile]]:
        """Scan all folders for reports and categorize them"""
        self.logger.info(f"Starting report discovery in {self.base_path}")
        
        report_patterns = [
            "*report*", "*REPORT*", "*.json", "*.md", "*.html", 
            "*results*", "*analysis*", "*test*", "*log*"
        ]
        
        discovered = {
            'test_results': [],
            'security_reports': [],
            'analysis_reports': [],
            'documentation': [],
            'logs': [],
            'other': []
        }
        
        for pattern in report_patterns:
            for file_path in self.base_path.rglob(pattern):
                if file_path.is_file() and not self._should_exclude(file_path):
                    report_file = self._create_report_file(file_path)
                    category = self._categorize_file(report_file)
                    discovered[category].append(report_file)
                    self.report_files.append(report_file)
        
        # Log discovery summary
        total_files = sum(len(files) for files in discovered.values())
        self.logger.info(f"Discovered {total_files} report files across {len(discovered)} categories")
        
        for category, files in discovered.items():
            if files:
                self.logger.info(f"  {category}: {len(files)} files")
        
        return discovered
    
    def _should_exclude(self, file_path: Path) -> bool:
        """Check if file should be excluded from processing"""
        exclude_patterns = [
            'node_modules', '.git', '__pycache__', '.venv', 'venv',
            '.pytest_cache', '.coverage', 'build', 'dist'
        ]
        
        return any(pattern in str(file_path) for pattern in exclude_patterns)
    
    def _create_report_file(self, file_path: Path) -> ReportFile:
        """Create ReportFile object from path"""
        stat = file_path.stat()
        file_type = file_path.suffix.lower().lstrip('.')
        
        return ReportFile(
            path=str(file_path),
            type=file_type or 'unknown',
            size=stat.st_size,
            modified=stat.st_mtime,
            errors=[],
            warnings=[],
            status='pending',
            agent_id=self.agent_id
        )
    
    def _categorize_file(self, report_file: ReportFile) -> str:
        """Categorize report file by path and content"""
        path_lower = report_file.path.lower()
        
        if 'test' in path_lower and ('result' in path_lower or 'report' in path_lower):
            return 'test_results'
        elif 'security' in path_lower:
            return 'security_reports'
        elif any(term in path_lower for term in ['analysis', 'audit', 'performance']):
            return 'analysis_reports'
        elif report_file.type in ['md', 'html'] and 'doc' in path_lower:
            return 'documentation'
        elif report_file.type in ['log', 'txt']:
            return 'logs'
        else:
            return 'other'

class ErrorAnalysisAgent:
    """Agent 2: Error/Warning Analysis Specialist"""
    
    def __init__(self):
        self.agent_id = "ERROR_ANALYSIS_AGENT_002"
        self.logger = logging.getLogger(f"Agent.{self.agent_id}")
        self.error_patterns = {
            'critical': [
                r'error:', r'ERROR:', r'CRITICAL:', r'FATAL:', r'exception:', 
                r'traceback', r'failed', r'FAILED', r'crash', r'abort'
            ],
            'warning': [
                r'warning:', r'WARNING:', r'WARN:', r'deprecated', r'DEPRECATED',
                r'notice:', r'NOTICE:', r'todo:', r'TODO:', r'fixme:', r'FIXME:'
            ]
        }
    
    async def analyze_reports(self, report_files: List[ReportFile]) -> Dict[str, List[ProcessingResult]]:
        """Analyze all reports for errors and warnings"""
        self.logger.info(f"Starting error analysis for {len(report_files)} files")
        
        results = {
            'critical_errors': [],
            'warnings': [],
            'clean_files': []
        }
        
        # Process files in parallel batches
        batch_size = 10
        for i in range(0, len(report_files), batch_size):
            batch = report_files[i:i + batch_size]
            batch_results = await self._process_batch(batch)
            
            for result in batch_results:
                if result.errors_found:
                    results['critical_errors'].append(result)
                elif result.warnings_found:
                    results['warnings'].append(result)
                else:
                    results['clean_files'].append(result)
        
        self.logger.info(f"Analysis complete: {len(results['critical_errors'])} critical, "
                        f"{len(results['warnings'])} warnings, {len(results['clean_files'])} clean")
        
        return results
    
    async def _process_batch(self, batch: List[ReportFile]) -> List[ProcessingResult]:
        """Process a batch of files concurrently"""
        loop = asyncio.get_event_loop()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                loop.run_in_executor(executor, self._analyze_file, report_file)
                for report_file in batch
            ]
            
            results = await asyncio.gather(*futures, return_exceptions=True)
            
            # Filter out exceptions and return valid results
            return [result for result in results if isinstance(result, ProcessingResult)]
    
    def _analyze_file(self, report_file: ReportFile) -> ProcessingResult:
        """Analyze individual file for errors and warnings"""
        start_time = datetime.datetime.now()
        
        try:
            with open(report_file.path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            errors = self._find_patterns(content, self.error_patterns['critical'])
            warnings = self._find_patterns(content, self.error_patterns['warning'])
            
            # Update report file metadata
            report_file.errors = errors
            report_file.warnings = warnings
            report_file.status = 'processed'
            
            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            
            return ProcessingResult(
                file_path=report_file.path,
                success=True,
                errors_found=errors,
                warnings_found=warnings,
                processing_time=processing_time,
                agent_id=self.agent_id
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing {report_file.path}: {e}")
            return ProcessingResult(
                file_path=report_file.path,
                success=False,
                errors_found=[f"Analysis failed: {str(e)}"],
                warnings_found=[],
                agent_id=self.agent_id
            )
    
    def _find_patterns(self, content: str, patterns: List[str]) -> List[str]:
        """Find matching patterns in content"""
        import re
        found = []
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Get surrounding context (50 chars before/after)
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end].replace('\n', ' ').strip()
                found.append(f"{pattern}: {context}")
        
        return found

class ArchiveOrganizationAgent:
    """Agent 3: Archive Organization Specialist"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.agent_id = "ARCHIVE_AGENT_003"
        self.logger = logging.getLogger(f"Agent.{self.agent_id}")
        self.archive_root = self.base_path / "reports" / "archives"
        self.timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
    def prepare_archive_structure(self, categories: Dict[str, List[ReportFile]]) -> Dict[str, Path]:
        """Create archive directory structure"""
        self.logger.info("Preparing archive structure")
        
        archive_dirs = {}
        base_archive = self.archive_root / f"archive_{self.timestamp}"
        
        for category in categories.keys():
            if categories[category]:  # Only create if files exist
                archive_dir = base_archive / category
                archive_dir.mkdir(parents=True, exist_ok=True)
                archive_dirs[category] = archive_dir
                self.logger.info(f"Created archive directory: {archive_dir}")
        
        # Create summary directory
        summary_dir = base_archive / "processing_summary"
        summary_dir.mkdir(parents=True, exist_ok=True)
        archive_dirs['summary'] = summary_dir
        
        return archive_dirs
    
    async def archive_files(self, report_files: List[ReportFile], 
                          archive_dirs: Dict[str, Path]) -> List[ProcessingResult]:
        """Archive processed files to appropriate directories"""
        self.logger.info(f"Starting archival of {len(report_files)} files")
        
        results = []
        
        # Process in parallel batches
        batch_size = 5
        for i in range(0, len(report_files), batch_size):
            batch = report_files[i:i + batch_size]
            batch_results = await self._archive_batch(batch, archive_dirs)
            results.extend(batch_results)
        
        self.logger.info(f"Archived {len([r for r in results if r.success])} files successfully")
        return results
    
    async def _archive_batch(self, batch: List[ReportFile], 
                           archive_dirs: Dict[str, Path]) -> List[ProcessingResult]:
        """Archive a batch of files"""
        loop = asyncio.get_event_loop()
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                loop.run_in_executor(executor, self._archive_file, report_file, archive_dirs)
                for report_file in batch
            ]
            
            results = await asyncio.gather(*futures, return_exceptions=True)
            return [result for result in results if isinstance(result, ProcessingResult)]
    
    def _archive_file(self, report_file: ReportFile, 
                     archive_dirs: Dict[str, Path]) -> ProcessingResult:
        """Archive individual file"""
        start_time = datetime.datetime.now()
        
        try:
            source_path = Path(report_file.path)
            
            # Determine target category and directory
            category = self._get_file_category(report_file)
            target_dir = archive_dirs.get(category, archive_dirs.get('other'))
            
            if not target_dir:
                raise ValueError(f"No archive directory for category: {category}")
            
            # Create unique filename to avoid conflicts
            target_path = target_dir / source_path.name
            counter = 1
            while target_path.exists():
                stem = source_path.stem
                suffix = source_path.suffix
                target_path = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            # Copy file to archive
            shutil.copy2(source_path, target_path)
            
            # Update report file status
            report_file.status = 'archived'
            
            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            
            self.logger.info(f"Archived: {source_path.name} -> {target_path}")
            
            return ProcessingResult(
                file_path=str(source_path),
                success=True,
                errors_found=[],
                warnings_found=[],
                archive_path=str(target_path),
                processing_time=processing_time,
                agent_id=self.agent_id
            )
            
        except Exception as e:
            self.logger.error(f"Error archiving {report_file.path}: {e}")
            return ProcessingResult(
                file_path=report_file.path,
                success=False,
                errors_found=[f"Archive failed: {str(e)}"],
                warnings_found=[],
                agent_id=self.agent_id
            )
    
    def _get_file_category(self, report_file: ReportFile) -> str:
        """Determine archive category for file"""
        path_lower = report_file.path.lower()
        
        if 'test' in path_lower and 'result' in path_lower:
            return 'test_results'
        elif 'security' in path_lower:
            return 'security_reports'
        elif 'analysis' in path_lower:
            return 'analysis_reports'
        elif report_file.type == 'md' and 'doc' in path_lower:
            return 'documentation'
        elif report_file.type in ['log', 'txt']:
            return 'logs'
        else:
            return 'other'

class ReportProcessingCoordinator:
    """Main coordinator for multi-agent report processing"""
    
    def __init__(self, base_path: str = "/home/kali/Desktop/AutoBot"):
        self.base_path = base_path
        self.logger = logging.getLogger("Coordinator")
        self.processing_start = datetime.datetime.now()
        
        # Initialize agents
        self.discovery_agent = ReportDiscoveryAgent(base_path)
        self.error_agent = ErrorAnalysisAgent()
        self.archive_agent = ArchiveOrganizationAgent(base_path)
        
        # Processing statistics
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'archived_files': 0,
            'errors_found': 0,
            'warnings_found': 0,
            'processing_time': 0.0
        }
    
    async def execute_processing_mission(self) -> Dict:
        """Execute the complete report processing mission"""
        self.logger.info("🚀 INITIATING REPORT PROCESSING MISSION")
        self.logger.info("=" * 60)
        
        try:
            # Phase 1: Discovery
            self.logger.info("📋 PHASE 1: Report Discovery")
            discovered_reports = self.discovery_agent.discover_reports()
            all_files = []
            for category_files in discovered_reports.values():
                all_files.extend(category_files)
            
            self.stats['total_files'] = len(all_files)
            self.logger.info(f"Discovered {len(all_files)} files for processing")
            
            # Phase 2: Error Analysis (Parallel)
            self.logger.info("🔍 PHASE 2: Error & Warning Analysis")
            analysis_results = await self.error_agent.analyze_reports(all_files)
            
            self.stats['errors_found'] = len(analysis_results['critical_errors'])
            self.stats['warnings_found'] = len(analysis_results['warnings'])
            self.stats['processed_files'] = len(all_files)
            
            # Phase 3: Archive Preparation
            self.logger.info("📁 PHASE 3: Archive Structure Preparation")
            archive_dirs = self.archive_agent.prepare_archive_structure(discovered_reports)
            
            # Phase 4: File Archival (Parallel)
            self.logger.info("📦 PHASE 4: File Archival")
            archive_results = await self.archive_agent.archive_files(all_files, archive_dirs)
            
            self.stats['archived_files'] = len([r for r in archive_results if r.success])
            
            # Phase 5: Generate Summary
            self.logger.info("📊 PHASE 5: Summary Generation")
            summary = await self._generate_comprehensive_summary(
                discovered_reports, analysis_results, archive_results, archive_dirs
            )
            
            # Calculate total processing time
            self.stats['processing_time'] = (datetime.datetime.now() - self.processing_start).total_seconds()
            
            self.logger.info("✅ MISSION COMPLETED SUCCESSFULLY")
            self.logger.info("=" * 60)
            self._log_final_statistics()
            
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ MISSION FAILED: {e}")
            raise
    
    async def _generate_comprehensive_summary(self, discovered_reports: Dict, 
                                            analysis_results: Dict, 
                                            archive_results: List,
                                            archive_dirs: Dict) -> Dict:
        """Generate comprehensive processing summary"""
        summary = {
            'mission_info': {
                'timestamp': self.processing_start.isoformat(),
                'duration_seconds': self.stats['processing_time'],
                'coordinator_id': 'AUTOBOT_REPORT_PROCESSOR'
            },
            'discovery_summary': {},
            'analysis_summary': {},
            'archive_summary': {},
            'statistics': self.stats,
            'recommendations': []
        }
        
        # Discovery summary
        for category, files in discovered_reports.items():
            summary['discovery_summary'][category] = {
                'file_count': len(files),
                'total_size_mb': sum(f.size for f in files) / (1024 * 1024),
                'file_types': list(set(f.type for f in files))
            }
        
        # Analysis summary
        summary['analysis_summary'] = {
            'critical_files': len(analysis_results['critical_errors']),
            'warning_files': len(analysis_results['warnings']),
            'clean_files': len(analysis_results['clean_files']),
            'top_error_patterns': self._get_top_error_patterns(analysis_results['critical_errors'])
        }
        
        # Archive summary
        summary['archive_summary'] = {
            'archive_location': str(self.archive_agent.archive_root / f"archive_{self.archive_agent.timestamp}"),
            'categories_created': list(archive_dirs.keys()),
            'successful_archives': len([r for r in archive_results if r.success]),
            'failed_archives': len([r for r in archive_results if not r.success])
        }
        
        # Generate recommendations
        summary['recommendations'] = self._generate_recommendations(analysis_results)
        
        # Save summary to file
        summary_path = archive_dirs['summary'] / 'processing_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Save detailed report
        report_path = archive_dirs['summary'] / 'detailed_processing_report.md'
        await self._save_detailed_report(summary, discovered_reports, analysis_results, report_path)
        
        return summary
    
    def _get_top_error_patterns(self, error_results: List) -> List[str]:
        """Get most common error patterns"""
        from collections import Counter
        
        all_errors = []
        for result in error_results:
            all_errors.extend(result.errors_found)
        
        # Extract pattern prefixes
        patterns = [error.split(':')[0] for error in all_errors if ':' in error]
        return [pattern for pattern, count in Counter(patterns).most_common(5)]
    
    def _generate_recommendations(self, analysis_results: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        if analysis_results['critical_errors']:
            recommendations.append(
                f"🔴 CRITICAL: {len(analysis_results['critical_errors'])} files contain errors requiring immediate attention"
            )
        
        if analysis_results['warnings']:
            recommendations.append(
                f"🟡 WARNING: {len(analysis_results['warnings'])} files have warnings that should be reviewed"
            )
        
        if len(analysis_results['clean_files']) > len(
            analysis_results['critical_errors']) + len(analysis_results['warnings']):
            recommendations.append(
                f"🟢 POSITIVE: {len(analysis_results['clean_files'])} files are clean and ready for production"
            )
        
        recommendations.extend([
            "📋 Review archived files in categorized directories",
            "🔍 Investigate critical error patterns identified",
            "📊 Use processing summary for future improvements",
            "🗂️ Consider automated monitoring for new reports"
        ])
        
        return recommendations
    
    async def _save_detailed_report(self, summary: Dict, discovered_reports: Dict, 
                                  analysis_results: Dict, report_path: Path):
        """Save detailed markdown report"""
        content = f"""# AutoBot Report Processing Summary

## Mission Overview
- **Timestamp**: {summary['mission_info']['timestamp']}
- **Duration**: {summary['statistics']['processing_time']:.2f} seconds
- **Total Files Processed**: {summary['statistics']['total_files']}

## Discovery Results

"""
        
        for category, info in summary['discovery_summary'].items():
            content += f"### {category.title().replace('_', ' ')}\n"
            content += f"- **Files**: {info['file_count']}\n"
            content += f"- **Size**: {info['total_size_mb']:.2f} MB\n"
            content += f"- **Types**: {', '.join(info['file_types'])}\n\n"
        
        content += f"""## Analysis Results

### Critical Errors: {summary['analysis_summary']['critical_files']} files
### Warnings: {summary['analysis_summary']['warning_files']} files  
### Clean Files: {summary['analysis_summary']['clean_files']} files

### Top Error Patterns
"""
        
        for pattern in summary['analysis_summary']['top_error_patterns']:
            content += f"- `{pattern}`\n"
        
        content += f"""

## Archive Summary

**Archive Location**: `{summary['archive_summary']['archive_location']}`

**Categories Created**:
"""
        
        for category in summary['archive_summary']['categories_created']:
            content += f"- {category}\n"
        
        content += f"""

## Recommendations

"""
        
        for rec in summary['recommendations']:
            content += f"- {rec}\n"
        
        content += f"""

## Processing Statistics

| Metric | Value |
|--------|--------|
| Total Files | {summary['statistics']['total_files']} |
| Processed Files | {summary['statistics']['processed_files']} |
| Archived Files | {summary['statistics']['archived_files']} |
| Errors Found | {summary['statistics']['errors_found']} |
| Warnings Found | {summary['statistics']['warnings_found']} |
| Processing Time | {summary['statistics']['processing_time']:.2f}s |

---
Generated by AutoBot Report Processing System
"""
        
        with open(report_path, 'w') as f:
            f.write(content)
    
    def _log_final_statistics(self):
        """Log final processing statistics"""
        self.logger.info("📊 FINAL PROCESSING STATISTICS:")
        self.logger.info(f"   Total Files: {self.stats['total_files']}")
        self.logger.info(f"   Processed: {self.stats['processed_files']}")
        self.logger.info(f"   Archived: {self.stats['archived_files']}")
        self.logger.info(f"   Errors Found: {self.stats['errors_found']}")
        self.logger.info(f"   Warnings Found: {self.stats['warnings_found']}")
        self.logger.info(f"   Total Time: {self.stats['processing_time']:.2f} seconds")

async def main():
    """Main execution function"""
    coordinator = ReportProcessingCoordinator()
    
    try:
        summary = await coordinator.execute_processing_mission()
        print("\n" + "="*60)
        print("🎯 MISSION ACCOMPLISHED!")
        print("="*60)
        print(f"✅ {summary['statistics']['total_files']} files processed")
        print(f"📦 {summary['statistics']['archived_files']} files archived")
        print(f"🔍 {summary['statistics']['errors_found']} critical issues found")
        print(f"⚠️  {summary['statistics']['warnings_found']} warnings identified")
        print(f"⏱️  Completed in {summary['statistics']['processing_time']:.2f} seconds")
        print(f"📁 Archive: {summary['archive_summary']['archive_location']}")
        
        return summary
        
    except Exception as e:
        logger.error(f"Mission failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())