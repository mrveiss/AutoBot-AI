"""
Frontend Code Analyzer
Extends the analysis suite to support JavaScript, TypeScript, Vue, React, and other frontend technologies
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import sys
from pathlib import Path

# Add AutoBot root to path for imports
autobot_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(autobot_root))

try:
    from src.utils.redis_client import get_redis_client
    from src.config import config
except ImportError:
    # Fallback for standalone usage
    def get_redis_client(async_client=False):
        return None
    
    class Config:
        def get(self, key, default=None):
            return default
    
    config = Config()

logger = logging.getLogger(__name__)


@dataclass
class FrontendComponent:
    """Represents a frontend component"""
    file_path: str
    component_type: str  # vue, react, angular, vanilla_js
    name: str
    line_number: int
    props: List[str]
    methods: List[str]
    lifecycle_hooks: List[str]
    dependencies: List[str]
    has_tests: bool
    accessibility_issues: List[str]
    performance_issues: List[str]


@dataclass
class FrontendIssue:
    """Represents a frontend-specific issue"""
    issue_type: str
    severity: str
    file_path: str
    line_number: int
    description: str
    suggestion: str
    framework: str  # vue, react, angular, etc.


class FrontendAnalyzer:
    """Analyzes frontend code for JavaScript, TypeScript, Vue, React, Angular"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config
        
        # Caching key
        self.FRONTEND_KEY = "frontend_analysis:results"
        
        # Framework detection patterns
        self.framework_patterns = {
            'vue': [
                r'<template>',
                r'export\s+default\s*{',
                r'Vue\.component',
                r'@Component',
                r'\.vue$'
            ],
            'react': [
                r'import\s+React',
                r'React\.Component',
                r'useState',
                r'useEffect',
                r'JSX\.Element'
            ],
            'angular': [
                r'@Component',
                r'@Injectable',
                r'import.*@angular',
                r'NgModule'
            ],
            'svelte': [
                r'<script>',
                r'\$:',
                r'export\s+let',
                r'\.svelte$'
            ]
        }
        
        # Frontend-specific issue patterns
        self.frontend_issues = {
            'security': [
                (r'innerHTML\s*=.*?\+', 'XSS via innerHTML concatenation', 'high'),
                (r'eval\s*\(', 'Code injection via eval', 'critical'),
                (r'document\.write\s*\(.*?\+', 'XSS via document.write', 'high'),
                (r'window\[.*?\]\s*\(', 'Dynamic function execution', 'medium'),
                (r'dangerouslySetInnerHTML', 'Potential XSS with dangerouslySetInnerHTML', 'medium'),
            ],
            'performance': [
                (r'console\.log', 'Console logging in production code', 'low'),
                (r'for\s*\(.*?document\.querySelector', 'DOM query in loop', 'high'),
                (r'setInterval\s*\(.*?[^c]lear', 'Potential memory leak with setInterval', 'medium'),
                (r'addEventListener.*?(?!removeEventListener)', 'Event listener without cleanup', 'medium'),
                (r'\.\$forceUpdate\s*\(', 'Vue: Avoid $forceUpdate', 'medium'),
                (r'componentWillMount', 'React: Deprecated lifecycle method', 'medium'),
            ],
            'accessibility': [
                (r'<img(?![^>]*alt\s*=)', 'Image without alt attribute', 'medium'),
                (r'<button(?![^>]*aria-label|title)', 'Button without accessible label', 'medium'),
                (r'onclick\s*=.*?(?!onkeydown)', 'Click handler without keyboard support', 'medium'),
                (r'<div.*?onclick', 'Non-semantic click handler', 'low'),
                (r'tabindex\s*=\s*["\']?\d+', 'Positive tabindex value', 'low'),
            ],
            'best_practices': [
                (r'var\s+', 'Use const/let instead of var', 'low'),
                (r'==\s*(?!null)', 'Use strict equality (===)', 'low'),
                (r'function\s*\(\s*\)\s*{.*?return.*?function', 'Consider arrow function', 'low'),
                (r'async\s+function.*?(?!await)', 'Async function without await', 'medium'),
                (r'catch\s*\(\s*\)\s*{', 'Empty catch block', 'medium'),
            ],
            'vue_specific': [
                (r'v-html\s*=.*?\+', 'Vue: XSS risk with v-html', 'high'),
                (r'\$refs\..*?\.focus\(\)', 'Vue: Direct DOM manipulation', 'low'),
                (r'this\.\$parent', 'Vue: Avoid $parent access', 'medium'),
                (r'v-for.*?:key\s*=\s*["\']index["\']', 'Vue: Avoid index as key', 'medium'),
            ],
            'react_specific': [
                (r'dangerouslySetInnerHTML.*?\+', 'React: XSS risk with dangerouslySetInnerHTML', 'critical'),
                (r'componentWillReceiveProps', 'React: Use componentDidUpdate', 'medium'),
                (r'findDOMNode', 'React: Deprecated findDOMNode', 'medium'),
                (r'setState.*?(?!callback)', 'React: setState without callback in async', 'low'),
            ]
        }
        
        logger.info("Frontend Analyzer initialized")
    
    async def analyze_frontend_code(self, root_path: str = ".", 
                                   patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze frontend code for issues and patterns"""
        
        start_time = time.time()
        patterns = patterns or [
            "**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx", 
            "**/*.vue", "**/*.svelte", "**/*.html"
        ]
        
        logger.info(f"Analyzing frontend code in {root_path}")
        
        # Discover frontend files and components
        components = await self._discover_frontend_components(root_path, patterns)
        
        # Analyze for issues
        issues = await self._analyze_frontend_issues(root_path, patterns)
        
        # Framework usage analysis
        framework_usage = self._analyze_framework_usage(components)
        
        # Performance analysis
        performance_analysis = await self._analyze_frontend_performance(components, issues)
        
        # Accessibility analysis
        accessibility_analysis = self._analyze_accessibility_issues(issues)
        
        # Security analysis
        security_analysis = self._analyze_frontend_security(issues)
        
        # Generate recommendations
        recommendations = self._generate_frontend_recommendations(issues, framework_usage)
        
        analysis_time = time.time() - start_time
        
        results = {
            "total_components": len(components),
            "total_issues": len(issues),
            "frameworks_detected": list(framework_usage.keys()),
            "analysis_time_seconds": analysis_time,
            "components": [self._serialize_component(c) for c in components],
            "issues": [self._serialize_issue(i) for i in issues],
            "framework_usage": framework_usage,
            "performance_analysis": performance_analysis,
            "accessibility_analysis": accessibility_analysis,
            "security_analysis": security_analysis,
            "recommendations": recommendations,
            "quality_score": self._calculate_frontend_quality_score(issues, components)
        }
        
        # Cache results
        await self._cache_results(results)
        
        logger.info(f"Frontend analysis complete in {analysis_time:.2f}s")
        return results
    
    async def _discover_frontend_components(self, root_path: str, 
                                          patterns: List[str]) -> List[FrontendComponent]:
        """Discover frontend components"""
        
        components = []
        root = Path(root_path)
        
        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path):
                    try:
                        component = await self._analyze_file_component(str(file_path))
                        if component:
                            components.append(component)
                    except Exception as e:
                        logger.warning(f"Failed to analyze {file_path}: {e}")
        
        return components
    
    async def _analyze_file_component(self, file_path: str) -> Optional[FrontendComponent]:
        """Analyze a single file as a frontend component"""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Detect framework
            framework = self._detect_framework(content, file_path)
            if not framework:
                return None
            
            # Extract component information
            component_name = Path(file_path).stem
            props = self._extract_props(content, framework)
            methods = self._extract_methods(content, framework)
            lifecycle_hooks = self._extract_lifecycle_hooks(content, framework)
            dependencies = self._extract_dependencies(content)
            has_tests = self._check_has_tests(file_path)
            
            return FrontendComponent(
                file_path=file_path,
                component_type=framework,
                name=component_name,
                line_number=1,
                props=props,
                methods=methods,
                lifecycle_hooks=lifecycle_hooks,
                dependencies=dependencies,
                has_tests=has_tests,
                accessibility_issues=[],
                performance_issues=[]
            )
        
        except Exception as e:
            logger.error(f"Error analyzing component {file_path}: {e}")
            return None
    
    def _detect_framework(self, content: str, file_path: str) -> Optional[str]:
        """Detect frontend framework"""
        
        # Check file extension first
        if file_path.endswith('.vue'):
            return 'vue'
        elif file_path.endswith('.svelte'):
            return 'svelte'
        
        # Check content patterns
        for framework, patterns in self.framework_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                    return framework
        
        # Default to vanilla JS/TS if it's a JS/TS file
        if any(file_path.endswith(ext) for ext in ['.js', '.ts', '.jsx', '.tsx']):
            return 'javascript'
        
        return None
    
    def _extract_props(self, content: str, framework: str) -> List[str]:
        """Extract component props based on framework"""
        
        props = []
        
        if framework == 'vue':
            # Vue props patterns
            prop_patterns = [
                r'props:\s*\[([^\]]+)\]',
                r'props:\s*{([^}]+)}',
                r'defineProps\<([^>]+)\>'
            ]
        elif framework == 'react':
            # React props patterns
            prop_patterns = [
                r'interface\s+\w+Props\s*{([^}]+)}',
                r'type\s+\w+Props\s*=\s*{([^}]+)}',
                r'function\s+\w+\s*\(\s*{\s*([^}]+)\s*}',
            ]
        else:
            prop_patterns = []
        
        for pattern in prop_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
            for match in matches:
                prop_content = match.group(1)
                # Extract individual prop names
                individual_props = re.findall(r'(\w+)', prop_content)
                props.extend(individual_props)
        
        return list(set(props))  # Remove duplicates
    
    def _extract_methods(self, content: str, framework: str) -> List[str]:
        """Extract component methods"""
        
        methods = []
        
        # General function patterns
        function_patterns = [
            r'(\w+)\s*:\s*function\s*\(',
            r'(\w+)\s*\([^)]*\)\s*{',
            r'function\s+(\w+)\s*\(',
            r'const\s+(\w+)\s*=\s*\([^)]*\)\s*=>',
            r'(\w+)\s*=\s*\([^)]*\)\s*=>'
        ]
        
        for pattern in function_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                method_name = match.group(1)
                if not method_name.startswith('_') and method_name.isalnum():
                    methods.append(method_name)
        
        return list(set(methods))
    
    def _extract_lifecycle_hooks(self, content: str, framework: str) -> List[str]:
        """Extract lifecycle hooks based on framework"""
        
        hooks = []
        
        if framework == 'vue':
            vue_hooks = [
                'created', 'mounted', 'updated', 'destroyed',
                'beforeCreate', 'beforeMount', 'beforeUpdate', 'beforeDestroy',
                'onMounted', 'onUpdated', 'onUnmounted'
            ]
            for hook in vue_hooks:
                if re.search(rf'\b{hook}\b', content):
                    hooks.append(hook)
        
        elif framework == 'react':
            react_hooks = [
                'componentDidMount', 'componentDidUpdate', 'componentWillUnmount',
                'useEffect', 'useState', 'useCallback', 'useMemo'
            ]
            for hook in react_hooks:
                if re.search(rf'\b{hook}\b', content):
                    hooks.append(hook)
        
        return hooks
    
    def _extract_dependencies(self, content: str) -> List[str]:
        """Extract import dependencies"""
        
        dependencies = []
        
        # Import patterns
        import_patterns = [
            r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]',
            r'import\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        ]
        
        for pattern in import_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                dep = match.group(1)
                if not dep.startswith('.'):  # External dependency
                    dependencies.append(dep.split('/')[0])  # Get package name
        
        return list(set(dependencies))
    
    def _check_has_tests(self, file_path: str) -> bool:
        """Check if component has associated tests"""
        
        file_path_obj = Path(file_path)
        test_patterns = [
            file_path_obj.parent / f"{file_path_obj.stem}.test.{file_path_obj.suffix[1:]}",
            file_path_obj.parent / f"{file_path_obj.stem}.spec.{file_path_obj.suffix[1:]}",
            file_path_obj.parent / "__tests__" / f"{file_path_obj.stem}.test.{file_path_obj.suffix[1:]}",
            file_path_obj.parent / "tests" / f"{file_path_obj.stem}.test.{file_path_obj.suffix[1:]}"
        ]
        
        return any(test_file.exists() for test_file in test_patterns)
    
    async def _analyze_frontend_issues(self, root_path: str, 
                                     patterns: List[str]) -> List[FrontendIssue]:
        """Analyze frontend code for issues"""
        
        issues = []
        root = Path(root_path)
        
        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path):
                    try:
                        file_issues = await self._analyze_file_issues(str(file_path))
                        issues.extend(file_issues)
                    except Exception as e:
                        logger.warning(f"Failed to analyze issues in {file_path}: {e}")
        
        return issues
    
    async def _analyze_file_issues(self, file_path: str) -> List[FrontendIssue]:
        """Analyze a single file for frontend issues"""
        
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            framework = self._detect_framework(content, file_path)
            if not framework:
                return issues
            
            # Analyze different issue categories
            for category, patterns in self.frontend_issues.items():
                # Skip framework-specific patterns for other frameworks
                if category.endswith('_specific') and not category.startswith(framework):
                    continue
                
                for pattern, description, severity in patterns:
                    for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                        line_num = content[:match.start()].count('\n') + 1
                        
                        issues.append(FrontendIssue(
                            issue_type=category,
                            severity=severity,
                            file_path=file_path,
                            line_number=line_num,
                            description=description,
                            suggestion=self._get_suggestion(category, description),
                            framework=framework
                        ))
        
        except Exception as e:
            logger.error(f"Error analyzing file issues {file_path}: {e}")
        
        return issues
    
    def _get_suggestion(self, category: str, description: str) -> str:
        """Get suggestion based on issue category and description"""
        
        suggestions = {
            'security': {
                'XSS': 'Use proper input sanitization and avoid innerHTML',
                'eval': 'Replace eval with safer alternatives like JSON.parse',
                'dangerouslySetInnerHTML': 'Sanitize content before using dangerouslySetInnerHTML'
            },
            'performance': {
                'console.log': 'Remove console.log statements in production',
                'DOM query in loop': 'Cache DOM queries outside loops',
                'setInterval': 'Always clear intervals with clearInterval'
            },
            'accessibility': {
                'alt attribute': 'Add descriptive alt attributes to images',
                'aria-label': 'Add aria-label or accessible text to buttons',
                'keyboard support': 'Add keyboard event handlers alongside mouse events'
            }
        }
        
        for key, desc_suggestions in suggestions.items():
            if key in category:
                for desc_key, suggestion in desc_suggestions.items():
                    if desc_key.lower() in description.lower():
                        return suggestion
        
        return "Review and fix this issue according to best practices"
    
    def _analyze_framework_usage(self, components: List[FrontendComponent]) -> Dict[str, Any]:
        """Analyze framework usage across components"""
        
        usage = {}
        
        for component in components:
            framework = component.component_type
            if framework not in usage:
                usage[framework] = {
                    'count': 0,
                    'components': [],
                    'common_patterns': []
                }
            
            usage[framework]['count'] += 1
            usage[framework]['components'].append(component.name)
            
            # Track common patterns
            if component.lifecycle_hooks:
                usage[framework].setdefault('lifecycle_hooks', []).extend(component.lifecycle_hooks)
        
        # Calculate percentages and clean up
        total_components = len(components)
        for framework, data in usage.items():
            data['percentage'] = (data['count'] / total_components * 100) if total_components > 0 else 0
            if 'lifecycle_hooks' in data:
                data['lifecycle_hooks'] = list(set(data['lifecycle_hooks']))
        
        return usage
    
    async def _analyze_frontend_performance(self, components: List[FrontendComponent],
                                          issues: List[FrontendIssue]) -> Dict[str, Any]:
        """Analyze frontend performance issues"""
        
        performance_issues = [i for i in issues if i.issue_type == 'performance']
        
        return {
            'total_performance_issues': len(performance_issues),
            'issues_by_type': self._group_issues_by_description(performance_issues),
            'components_with_issues': len([c for c in components if any(
                i.file_path == c.file_path for i in performance_issues
            )]),
            'recommendations': [
                'Remove console.log statements from production code',
                'Cache DOM queries outside of loops',
                'Clean up event listeners and intervals',
                'Optimize component re-rendering'
            ]
        }
    
    def _analyze_accessibility_issues(self, issues: List[FrontendIssue]) -> Dict[str, Any]:
        """Analyze accessibility issues"""
        
        a11y_issues = [i for i in issues if i.issue_type == 'accessibility']
        
        return {
            'total_accessibility_issues': len(a11y_issues),
            'issues_by_severity': self._group_issues_by_severity(a11y_issues),
            'wcag_compliance_score': max(0, 100 - len(a11y_issues) * 5),  # Rough scoring
            'recommendations': [
                'Add alt attributes to all images',
                'Ensure keyboard navigation support',
                'Use semantic HTML elements',
                'Test with screen readers'
            ]
        }
    
    def _analyze_frontend_security(self, issues: List[FrontendIssue]) -> Dict[str, Any]:
        """Analyze frontend security issues"""
        
        security_issues = [i for i in issues if i.issue_type == 'security']
        
        return {
            'total_security_issues': len(security_issues),
            'critical_issues': len([i for i in security_issues if i.severity == 'critical']),
            'high_priority_issues': len([i for i in security_issues if i.severity == 'high']),
            'security_score': max(0, 100 - len([i for i in security_issues if i.severity in ['critical', 'high']]) * 20),
            'recommendations': [
                'Sanitize all user inputs',
                'Avoid dangerouslySetInnerHTML with user content',
                'Use Content Security Policy (CSP)',
                'Validate data on both client and server'
            ]
        }
    
    def _generate_frontend_recommendations(self, issues: List[FrontendIssue],
                                         framework_usage: Dict[str, Any]) -> List[str]:
        """Generate frontend-specific recommendations"""
        
        recommendations = []
        
        # Security recommendations
        security_issues = [i for i in issues if i.issue_type == 'security']
        if security_issues:
            recommendations.append(f"🛡️ Fix {len(security_issues)} security issues to prevent XSS and code injection")
        
        # Performance recommendations
        perf_issues = [i for i in issues if i.issue_type == 'performance']
        if perf_issues:
            recommendations.append(f"⚡ Optimize {len(perf_issues)} performance issues for better user experience")
        
        # Accessibility recommendations
        a11y_issues = [i for i in issues if i.issue_type == 'accessibility']
        if a11y_issues:
            recommendations.append(f"♿ Address {len(a11y_issues)} accessibility issues for better inclusion")
        
        # Framework-specific recommendations
        if 'vue' in framework_usage:
            recommendations.append("🔧 Consider Vue 3 Composition API for better code organization")
        
        if 'react' in framework_usage:
            recommendations.append("🔧 Use React Hooks and avoid deprecated lifecycle methods")
        
        # General recommendations
        recommendations.extend([
            "📱 Implement responsive design testing",
            "🧪 Add component unit tests for better reliability",
            "📊 Set up frontend performance monitoring",
            "🔍 Use ESLint and Prettier for code quality"
        ])
        
        return recommendations
    
    def _calculate_frontend_quality_score(self, issues: List[FrontendIssue],
                                        components: List[FrontendComponent]) -> float:
        """Calculate overall frontend quality score"""
        
        if not components:
            return 0.0
        
        # Base score
        score = 100.0
        
        # Deduct points for issues by severity
        for issue in issues:
            if issue.severity == 'critical':
                score -= 20
            elif issue.severity == 'high':
                score -= 10
            elif issue.severity == 'medium':
                score -= 5
            elif issue.severity == 'low':
                score -= 2
        
        # Bonus for testing
        tested_components = len([c for c in components if c.has_tests])
        test_coverage = tested_components / len(components)
        score += test_coverage * 10  # Up to 10 bonus points
        
        return max(0.0, min(100.0, score))
    
    def _group_issues_by_description(self, issues: List[FrontendIssue]) -> Dict[str, int]:
        """Group issues by description"""
        groups = {}
        for issue in issues:
            groups[issue.description] = groups.get(issue.description, 0) + 1
        return groups
    
    def _group_issues_by_severity(self, issues: List[FrontendIssue]) -> Dict[str, int]:
        """Group issues by severity"""
        groups = {}
        for issue in issues:
            groups[issue.severity] = groups.get(issue.severity, 0) + 1
        return groups
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "node_modules", ".git", "dist", "build", ".nuxt", ".next",
            "coverage", ".coverage", "__pycache__", ".venv", "venv"
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)
    
    def _serialize_component(self, component: FrontendComponent) -> Dict[str, Any]:
        """Serialize component for output"""
        return {
            "file_path": component.file_path,
            "component_type": component.component_type,
            "name": component.name,
            "line_number": component.line_number,
            "props": component.props,
            "methods": component.methods,
            "lifecycle_hooks": component.lifecycle_hooks,
            "dependencies": component.dependencies,
            "has_tests": component.has_tests,
            "accessibility_issues": component.accessibility_issues,
            "performance_issues": component.performance_issues
        }
    
    def _serialize_issue(self, issue: FrontendIssue) -> Dict[str, Any]:
        """Serialize issue for output"""
        return {
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "description": issue.description,
            "suggestion": issue.suggestion,
            "framework": issue.framework
        }
    
    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results"""
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    self.FRONTEND_KEY,
                    3600,
                    json.dumps(results, default=str)
                )
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")


async def main():
    """Example usage of frontend analyzer"""
    
    analyzer = FrontendAnalyzer()
    
    # Analyze frontend code
    results = await analyzer.analyze_frontend_code(
        root_path=".",
        patterns=["**/*.js", "**/*.ts", "**/*.vue", "**/*.jsx", "**/*.tsx"]
    )
    
    print(f"\n=== Frontend Code Analysis Results ===")
    print(f"Total components: {results['total_components']}")
    print(f"Total issues: {results['total_issues']}")
    print(f"Frameworks detected: {', '.join(results['frameworks_detected'])}")
    print(f"Quality score: {results['quality_score']:.1f}/100")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")
    
    # Framework usage
    print(f"\n=== Framework Usage ===")
    for framework, usage in results['framework_usage'].items():
        print(f"{framework}: {usage['count']} components ({usage['percentage']:.1f}%)")
    
    # Issues by category
    categories = ['security', 'performance', 'accessibility', 'best_practices']
    for category in categories:
        category_issues = [i for i in results['issues'] if i['issue_type'] == category]
        if category_issues:
            print(f"\n=== {category.replace('_', ' ').title()} Issues ===")
            for issue in category_issues[:5]:  # Show first 5
                print(f"• {issue['description']} ({issue['file_path']}:{issue['line_number']})")


if __name__ == "__main__":
    asyncio.run(main())