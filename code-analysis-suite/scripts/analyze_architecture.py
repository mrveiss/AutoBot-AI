#!/usr/bin/env python3
"""
Analyze AutoBot codebase for architectural patterns and design quality
"""

import asyncio
import json
from pathlib import Path

from src.architectural_pattern_analyzer import ArchitecturalPatternAnalyzer


async def analyze_architectural_patterns():
    """Analyze codebase for architectural patterns and design issues"""
    
    print("🏗️ Starting architectural pattern analysis...")
    
    analyzer = ArchitecturalPatternAnalyzer()
    
    # Run analysis
    results = await analyzer.analyze_architecture(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"]
    )
    
    print("\n=== Architectural Pattern Analysis Results ===\n")
    
    # Summary
    print(f"📊 **Analysis Summary:**")
    print(f"   - Total components: {results['total_components']}")
    print(f"   - Architectural issues: {results['architectural_issues']}")
    print(f"   - Design patterns found: {results['design_patterns_found']}")
    print(f"   - Architecture score: {results['architecture_score']}/100")
    print(f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n")
    
    # Detailed metrics
    metrics = results['metrics']
    print("🏛️ **Architectural Quality Metrics:**")
    print(f"   - Coupling score: {metrics['coupling_score']}/100 (lower coupling is better)")
    print(f"   - Cohesion score: {metrics['cohesion_score']}/100")
    print(f"   - Pattern adherence: {metrics['pattern_adherence_score']}/100")
    print(f"   - Maintainability index: {metrics['maintainability_index']}/100")
    print(f"   - Abstraction score: {metrics['abstraction_score']}/100")
    print(f"   - Instability score: {metrics['instability_score']}/100")
    print()
    
    # Component breakdown
    component_types = {}
    for comp in results['components']:
        comp_type = comp['type']
        component_types[comp_type] = component_types.get(comp_type, 0) + 1
    
    print("🧩 **Component Breakdown:**")
    for comp_type, count in component_types.items():
        print(f"   - {comp_type.title()}s: {count}")
    print()
    
    # Design patterns detected
    if results['detected_patterns']:
        pattern_counts = {}
        for pattern in results['detected_patterns']:
            pattern_name = pattern['pattern']
            pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1
        
        print("🎨 **Design Patterns Detected:**")
        for pattern, count in sorted(pattern_counts.items()):
            print(f"   - {pattern.replace('_', ' ').title()}: {count} instances")
        
        print("\n📋 **Pattern Details:**")
        for pattern in results['detected_patterns'][:10]:  # Show first 10
            print(f"   - {pattern['pattern'].title()} in {pattern['file']}:{pattern['line']}")
            print(f"     {pattern['description']}")
        print()
    
    # Architectural issues
    if results['architectural_issues']:
        print("🚨 **Architectural Issues:**")
        for issue in results['architectural_issues']:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue['severity'], "⚪")
            
            print(f"\n   {emoji} **{issue['type'].replace('_', ' ').title()}** ({issue['severity']})")
            print(f"      {issue['description']}")
            print(f"      Affects: {issue['affected_components_count']} components")
            print(f"      💡 Suggestion: {issue['suggestion']}")
            print(f"      🔧 Refactoring effort: {issue['refactoring_effort']}")
            if issue['pattern_violation']:
                print(f"      ❌ Violates: {issue['pattern_violation']}")
    
    # High coupling analysis
    high_coupling_components = [c for c in results['components'] if c['coupling_score'] > 10]
    if high_coupling_components:
        print(f"\n🔗 **High Coupling Analysis:**")
        print(f"   Found {len(high_coupling_components)} components with high coupling:")
        for comp in high_coupling_components[:5]:  # Show top 5
            print(f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}")
            print(f"     Coupling score: {comp['coupling_score']} dependencies")
            print(f"     Dependencies: {', '.join(comp['dependencies'][:5])}")
            if len(comp['dependencies']) > 5:
                print(f"     ... and {len(comp['dependencies']) - 5} more")
        print()
    
    # Low cohesion analysis
    low_cohesion_classes = [c for c in results['components'] 
                          if c['type'] == 'class' and c['cohesion_score'] < 0.3]
    if low_cohesion_classes:
        print(f"🔄 **Low Cohesion Analysis:**")
        print(f"   Found {len(low_cohesion_classes)} classes with low cohesion:")
        for comp in low_cohesion_classes[:5]:
            print(f"   - Class '{comp['name']}' in {comp['file']}")
            print(f"     Cohesion score: {comp['cohesion_score']:.2f}")
            print(f"     Interfaces: {len(comp['interfaces'])} methods")
        print()
    
    # Complex components
    complex_components = [c for c in results['components'] if c['complexity_score'] > 20]
    if complex_components:
        print(f"🧠 **High Complexity Analysis:**")
        print(f"   Found {len(complex_components)} highly complex components:")
        for comp in complex_components[:5]:
            print(f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}")
            print(f"     Complexity score: {comp['complexity_score']}")
            if comp['patterns']:
                print(f"     Patterns: {', '.join(comp['patterns'])}")
        print()
    
    # Save detailed report
    report_path = Path("architectural_analysis_report.json")
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"📋 Detailed report saved to: {report_path}")
    
    # Generate architecture recommendations
    await generate_architecture_recommendations(results)
    
    return results


async def generate_architecture_recommendations(results):
    """Generate specific architectural improvement recommendations"""
    
    print("\n=== Architectural Improvement Recommendations ===\n")
    
    recommendations = results['recommendations']
    
    if recommendations:
        print("🏗️ **Priority Recommendations:**")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
        print()
    
    # Specific improvement patterns
    print("🛠️ **Architectural Improvement Patterns:**\n")
    
    # SOLID Principles
    print("**1. SOLID Principles Application:**")
    print("```python")
    print("# ❌ God class violating SRP")
    print("class UserManager:")
    print("    def create_user(self): pass")
    print("    def send_email(self): pass")
    print("    def log_action(self): pass")
    print("    def validate_data(self): pass")
    print()
    print("# ✅ Separated responsibilities")
    print("class UserService:")
    print("    def create_user(self): pass")
    print()
    print("class EmailService:")
    print("    def send_email(self): pass")
    print()
    print("class Logger:")
    print("    def log_action(self): pass")
    print()
    print("class Validator:")
    print("    def validate_data(self): pass")
    print("```")
    print()
    
    # Dependency Injection
    print("**2. Dependency Injection Pattern:**")
    print("```python")
    print("# ❌ Tight coupling")
    print("class OrderService:")
    print("    def __init__(self):")
    print("        self.db = MySQLDatabase()  # Hard dependency")
    print("        self.email = SMTPEmailService()  # Hard dependency")
    print()
    print("# ✅ Dependency injection")
    print("from abc import ABC, abstractmethod")
    print()
    print("class DatabaseInterface(ABC):")
    print("    @abstractmethod")
    print("    def save(self, data): pass")
    print()
    print("class OrderService:")
    print("    def __init__(self, db: DatabaseInterface, email_service):")
    print("        self.db = db  # Injected dependency")
    print("        self.email = email_service  # Injected dependency")
    print("```")
    print()
    
    # Observer Pattern
    print("**3. Observer Pattern for Event Handling:**")
    print("```python")
    print("# ❌ Tight coupling between components")
    print("class User:")
    print("    def update_profile(self):")
    print("        # Direct calls to other services")
    print("        email_service.send_notification()")
    print("        audit_service.log_change()")
    print("        cache_service.invalidate()")
    print()
    print("# ✅ Observer pattern")
    print("class EventBus:")
    print("    def __init__(self):")
    print("        self.observers = []")
    print("    ")
    print("    def subscribe(self, observer):")
    print("        self.observers.append(observer)")
    print("    ")
    print("    def notify(self, event):")
    print("        for observer in self.observers:")
    print("            observer.handle(event)")
    print()
    print("class User:")
    print("    def update_profile(self):")
    print("        # Publish event instead of direct coupling")
    print("        event_bus.notify(ProfileUpdatedEvent(self))")
    print("```")
    print()
    
    # Factory Pattern
    print("**4. Factory Pattern for Object Creation:**")
    print("```python")
    print("# ❌ Complex object creation scattered everywhere")
    print("if config_type == 'development':")
    print("    db = SqliteDatabase()")
    print("elif config_type == 'production':")
    print("    db = PostgresDatabase()")
    print()
    print("# ✅ Factory pattern")
    print("class DatabaseFactory:")
    print("    @staticmethod")
    print("    def create_database(config_type: str):")
    print("        if config_type == 'development':")
    print("            return SqliteDatabase()")
    print("        elif config_type == 'production':")
    print("            return PostgresDatabase()")
    print("        else:")
    print("            raise ValueError(f'Unknown config type: {config_type}')")
    print("```")
    print()
    
    # Layered Architecture
    print("**5. Layered Architecture Pattern:**")
    print("```")
    print("src/")
    print("├── presentation/     # Controllers, API endpoints")
    print("├── application/      # Use cases, application services")
    print("├── domain/          # Business logic, entities")
    print("└── infrastructure/  # Database, external services")
    print()
    print("# Dependency flow: Presentation -> Application -> Domain")
    print("# Infrastructure depends on Domain (Dependency Inversion)")
    print("```")
    print()
    
    # Repository Pattern
    print("**6. Repository Pattern for Data Access:**")
    print("```python")
    print("# ❌ Direct database calls in business logic")
    print("class UserService:")
    print("    def get_user(self, user_id):")
    print("        cursor.execute('SELECT * FROM users WHERE id = %s', user_id)")
    print("        return cursor.fetchone()")
    print()
    print("# ✅ Repository pattern")
    print("class UserRepository(ABC):")
    print("    @abstractmethod")
    print("    def get_by_id(self, user_id: int) -> User: pass")
    print("    ")
    print("    @abstractmethod")
    print("    def save(self, user: User): pass")
    print()
    print("class UserService:")
    print("    def __init__(self, user_repo: UserRepository):")
    print("        self.user_repo = user_repo")
    print("    ")
    print("    def get_user(self, user_id: int) -> User:")
    print("        return self.user_repo.get_by_id(user_id)")
    print("```")
    print()


async def demonstrate_architecture_testing():
    """Show how to add architectural tests"""
    
    print("=== Architectural Testing Setup ===\n")
    
    print("🧪 **Add Architectural Tests:**")
    print()
    
    print("**1. Dependency Rules Testing:**")
    print("```python")
    print("import ast")
    print("from pathlib import Path")
    print()
    print("def test_layer_dependencies():")
    print("    \"\"\"Test that presentation layer doesn't import from infrastructure\"\"\"")
    print("    presentation_files = list(Path('src/presentation').glob('**/*.py'))")
    print("    ")
    print("    for file_path in presentation_files:")
    print("        with open(file_path) as f:")
    print("            tree = ast.parse(f.read())")
    print("        ")
    print("        for node in ast.walk(tree):")
    print("            if isinstance(node, ast.ImportFrom):")
    print("                if node.module and 'infrastructure' in node.module:")
    print("                    assert False, f'{file_path} imports from infrastructure'")
    print("```")
    print()
    
    print("**2. Complexity Monitoring:**")
    print("```python")
    print("def test_class_complexity():")
    print("    \"\"\"Ensure classes don't exceed complexity thresholds\"\"\"")
    print("    for file_path in Path('src').rglob('*.py'):")
    print("        with open(file_path) as f:")
    print("            tree = ast.parse(f.read())")
    print("        ")
    print("        for node in ast.walk(tree):")
    print("            if isinstance(node, ast.ClassDef):")
    print("                method_count = len([n for n in node.body if isinstance(n, ast.FunctionDef)])")
    print("                assert method_count < 20, f'Class {node.name} has {method_count} methods'")
    print("```")
    print()
    
    print("**3. Pattern Enforcement:**")
    print("```python")
    print("def test_singleton_pattern():")
    print("    \"\"\"Ensure singletons are properly implemented\"\"\"")
    print("    singleton_files = find_singleton_classes()")
    print("    ")
    print("    for file_path, class_name in singleton_files:")
    print("        # Verify __new__ method is implemented")
    print("        # Verify thread safety")
    print("        # Verify instance management")
    print("        pass")
    print("```")
    print()


async def main():
    """Run the architectural pattern analysis"""
    
    # Analyze architectural patterns
    results = await analyze_architectural_patterns()
    
    # Show architectural testing setup
    await demonstrate_architecture_testing()
    
    print("\n=== Analysis Complete ===")
    print("Next steps:")
    print("1. Review architectural_analysis_report.json for detailed findings")
    print("2. Fix high-severity architectural issues first")
    print("3. Reduce coupling in highly-coupled components")
    print("4. Improve cohesion in low-cohesion classes")
    print("5. Apply appropriate design patterns")
    print("6. Add architectural tests to enforce design rules")


if __name__ == "__main__":
    asyncio.run(main())