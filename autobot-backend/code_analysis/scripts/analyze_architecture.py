#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analyze AutoBot codebase for architectural patterns and design quality

NOTE: generate_architecture_recommendations (~155 lines) is an ACCEPTABLE EXCEPTION
per Issue #490 - analysis output generator with sequential logic. Low priority.
"""

import asyncio
import json
from pathlib import Path

from architectural_pattern_analyzer import ArchitecturalPatternAnalyzer


async def analyze_architectural_patterns():
    """Analyze codebase for architectural patterns and design issues"""

    print("🏗️ Starting architectural pattern analysis...")  # noqa: print

    analyzer = ArchitecturalPatternAnalyzer()

    # Run analysis
    results = await analyzer.analyze_architecture(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    print("\n=== Architectural Pattern Analysis Results ===\n")  # noqa: print

    # Summary
    print(f"📊 **Analysis Summary:**")  # noqa: print
    print(f"   - Total components: {results['total_components']}")  # noqa: print
    print(
        f"   - Architectural issues: {results['architectural_issues']}"
    )  # noqa: print
    print(
        f"   - Design patterns found: {results['design_patterns_found']}"
    )  # noqa: print
    print(
        f"   - Architecture score: {results['architecture_score']}/100"
    )  # noqa: print
    print(
        f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n"
    )  # noqa: print

    # Detailed metrics
    metrics = results["metrics"]
    print("🏛️ **Architectural Quality Metrics:**")  # noqa: print
    print(  # noqa: print
        f"   - Coupling score: {metrics['coupling_score']}/100 (lower coupling is better)"
    )
    print(f"   - Cohesion score: {metrics['cohesion_score']}/100")  # noqa: print
    print(
        f"   - Pattern adherence: {metrics['pattern_adherence_score']}/100"
    )  # noqa: print
    print(
        f"   - Maintainability index: {metrics['maintainability_index']}/100"
    )  # noqa: print
    print(f"   - Abstraction score: {metrics['abstraction_score']}/100")  # noqa: print
    print(f"   - Instability score: {metrics['instability_score']}/100")  # noqa: print
    print()  # noqa: print

    # Component breakdown
    component_types = {}
    for comp in results["components"]:
        comp_type = comp["type"]
        component_types[comp_type] = component_types.get(comp_type, 0) + 1

    print("🧩 **Component Breakdown:**")  # noqa: print
    for comp_type, count in component_types.items():
        print(f"   - {comp_type.title()}s: {count}")  # noqa: print
    print()  # noqa: print

    # Design patterns detected
    if results["detected_patterns"]:
        pattern_counts = {}
        for pattern in results["detected_patterns"]:
            pattern_name = pattern["pattern"]
            pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1

        print("🎨 **Design Patterns Detected:**")  # noqa: print
        for pattern, count in sorted(pattern_counts.items()):
            print(
                f"   - {pattern.replace('_', ' ').title()}: {count} instances"
            )  # noqa: print

        print("\n📋 **Pattern Details:**")  # noqa: print
        for pattern in results["detected_patterns"][:10]:  # Show first 10
            print(  # noqa: print
                f"   - {pattern['pattern'].title()} in {pattern['file']}:{pattern['line']}"
            )
            print(f"     {pattern['description']}")  # noqa: print
        print()  # noqa: print

    # Architectural issues
    if results["architectural_issues"]:
        print("🚨 **Architectural Issues:**")  # noqa: print
        for issue in results["architectural_issues"]:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue["severity"], "⚪")

            print(  # noqa: print
                f"\n   {emoji} **{issue['type'].replace('_', ' ').title()}** ({issue['severity']})"
            )
            print(f"      {issue['description']}")  # noqa: print
            print(
                f"      Affects: {issue['affected_components_count']} components"
            )  # noqa: print
            print(f"      💡 Suggestion: {issue['suggestion']}")  # noqa: print
            print(
                f"      🔧 Refactoring effort: {issue['refactoring_effort']}"
            )  # noqa: print
            if issue["pattern_violation"]:
                print(f"      ❌ Violates: {issue['pattern_violation']}")  # noqa: print

    # High coupling analysis
    high_coupling_components = [
        c for c in results["components"] if c["coupling_score"] > 10
    ]
    if high_coupling_components:
        print(f"\n🔗 **High Coupling Analysis:**")  # noqa: print
        print(  # noqa: print
            f"   Found {len(high_coupling_components)} components with high coupling:"
        )
        for comp in high_coupling_components[:5]:  # Show top 5
            print(
                f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}"
            )  # noqa: print
            print(
                f"     Coupling score: {comp['coupling_score']} dependencies"
            )  # noqa: print
            print(
                f"     Dependencies: {', '.join(comp['dependencies'][:5])}"
            )  # noqa: print
            if len(comp["dependencies"]) > 5:
                print(
                    f"     ... and {len(comp['dependencies']) - 5} more"
                )  # noqa: print
        print()  # noqa: print

    # Low cohesion analysis
    low_cohesion_classes = [
        c
        for c in results["components"]
        if c["type"] == "class" and c["cohesion_score"] < 0.3
    ]
    if low_cohesion_classes:
        print(f"🔄 **Low Cohesion Analysis:**")  # noqa: print
        print(
            f"   Found {len(low_cohesion_classes)} classes with low cohesion:"
        )  # noqa: print
        for comp in low_cohesion_classes[:5]:
            print(f"   - Class '{comp['name']}' in {comp['file']}")  # noqa: print
            print(f"     Cohesion score: {comp['cohesion_score']:.2f}")  # noqa: print
            print(f"     Interfaces: {len(comp['interfaces'])} methods")  # noqa: print
        print()  # noqa: print

    # Complex components
    complex_components = [
        c for c in results["components"] if c["complexity_score"] > 20
    ]
    if complex_components:
        print(f"🧠 **High Complexity Analysis:**")  # noqa: print
        print(
            f"   Found {len(complex_components)} highly complex components:"
        )  # noqa: print
        for comp in complex_components[:5]:
            print(
                f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}"
            )  # noqa: print
            print(f"     Complexity score: {comp['complexity_score']}")  # noqa: print
            if comp["patterns"]:
                print(f"     Patterns: {', '.join(comp['patterns'])}")  # noqa: print
        print()  # noqa: print

    # Save detailed report
    report_path = Path("architectural_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"📋 Detailed report saved to: {report_path}")  # noqa: print

    # Generate architecture recommendations
    await generate_architecture_recommendations(results)

    return results


async def generate_architecture_recommendations(results):
    """Generate specific architectural improvement recommendations"""

    print("\n=== Architectural Improvement Recommendations ===\n")  # noqa: print

    recommendations = results["recommendations"]

    if recommendations:
        print("🏗️ **Priority Recommendations:**")  # noqa: print
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")  # noqa: print
        print()  # noqa: print

    # Specific improvement patterns
    print("🛠️ **Architectural Improvement Patterns:**\n")  # noqa: print

    # SOLID Principles
    print("**1. SOLID Principles Application:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ God class violating SRP")  # noqa: print
    print("class UserManager:")  # noqa: print
    print("    def create_user(self): pass")  # noqa: print
    print("    def send_email(self): pass")  # noqa: print
    print("    def log_action(self): pass")  # noqa: print
    print("    def validate_data(self): pass")  # noqa: print
    print()  # noqa: print
    print("# ✅ Separated responsibilities")  # noqa: print
    print("class UserService:")  # noqa: print
    print("    def create_user(self): pass")  # noqa: print
    print()  # noqa: print
    print("class EmailService:")  # noqa: print
    print("    def send_email(self): pass")  # noqa: print
    print()  # noqa: print
    print("class Logger:")  # noqa: print
    print("    def log_action(self): pass")  # noqa: print
    print()  # noqa: print
    print("class Validator:")  # noqa: print
    print("    def validate_data(self): pass")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Dependency Injection
    print("**2. Dependency Injection Pattern:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Tight coupling")  # noqa: print
    print("class OrderService:")  # noqa: print
    print("    def __init__(self):")  # noqa: print
    print("        self.db = MySQLDatabase()  # Hard dependency")  # noqa: print
    print("        self.email = SMTPEmailService()  # Hard dependency")  # noqa: print
    print()  # noqa: print
    print("# ✅ Dependency injection")  # noqa: print
    print("from abc import ABC, abstractmethod")  # noqa: print
    print()  # noqa: print
    print("class DatabaseInterface(ABC):")  # noqa: print
    print("    @abstractmethod")  # noqa: print
    print("    def save(self, data): pass")  # noqa: print
    print()  # noqa: print
    print("class OrderService:")  # noqa: print
    print(
        "    def __init__(self, db: DatabaseInterface, email_service):"
    )  # noqa: print
    print("        self.db = db  # Injected dependency")  # noqa: print
    print("        self.email = email_service  # Injected dependency")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Observer Pattern
    print("**3. Observer Pattern for Event Handling:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Tight coupling between components")  # noqa: print
    print("class User:")  # noqa: print
    print("    def update_profile(self):")  # noqa: print
    print("        # Direct calls to other services")  # noqa: print
    print("        email_service.send_notification()")  # noqa: print
    print("        audit_service.log_change()")  # noqa: print
    print("        cache_service.invalidate()")  # noqa: print
    print()  # noqa: print
    print("# ✅ Observer pattern")  # noqa: print
    print("class EventBus:")  # noqa: print
    print("    def __init__(self):")  # noqa: print
    print("        self.observers = []")  # noqa: print
    print("    ")  # noqa: print
    print("    def subscribe(self, observer):")  # noqa: print
    print("        self.observers.append(observer)")  # noqa: print
    print("    ")  # noqa: print
    print("    def notify(self, event):")  # noqa: print
    print("        for observer in self.observers:")  # noqa: print
    print("            observer.handle(event)")  # noqa: print
    print()  # noqa: print
    print("class User:")  # noqa: print
    print("    def update_profile(self):")  # noqa: print
    print("        # Publish event instead of direct coupling")  # noqa: print
    print("        event_bus.notify(ProfileUpdatedEvent(self))")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Factory Pattern
    print("**4. Factory Pattern for Object Creation:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Complex object creation scattered everywhere")  # noqa: print
    print("if config_type == 'development':")  # noqa: print
    print("    db = SqliteDatabase()")  # noqa: print
    print("elif config_type == 'production':")  # noqa: print
    print("    db = PostgresDatabase()")  # noqa: print
    print()  # noqa: print
    print("# ✅ Factory pattern")  # noqa: print
    print("class DatabaseFactory:")  # noqa: print
    print("    @staticmethod")  # noqa: print
    print("    def create_database(config_type: str):")  # noqa: print
    print("        if config_type == 'development':")  # noqa: print
    print("            return SqliteDatabase()")  # noqa: print
    print("        elif config_type == 'production':")  # noqa: print
    print("            return PostgresDatabase()")  # noqa: print
    print("        else:")  # noqa: print
    print(
        "            raise ValueError(f'Unknown config type: {config_type}')"
    )  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Layered Architecture
    print("**5. Layered Architecture Pattern:**")  # noqa: print
    print("```")  # noqa: print
    print("src/")  # noqa: print
    print("├── presentation/     # Controllers, API endpoints")  # noqa: print
    print("├── application/      # Use cases, application services")  # noqa: print
    print("├── domain/          # Business logic, entities")  # noqa: print
    print("└── infrastructure/  # Database, external services")  # noqa: print
    print()  # noqa: print
    print("# Dependency flow: Presentation -> Application -> Domain")  # noqa: print
    print("# Infrastructure depends on Domain (Dependency Inversion)")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print

    # Repository Pattern
    print("**6. Repository Pattern for Data Access:**")  # noqa: print
    print("```python")  # noqa: print
    print("# ❌ Direct database calls in business logic")  # noqa: print
    print("class UserService:")  # noqa: print
    print("    def get_user(self, user_id):")  # noqa: print
    print(
        "        cursor.execute('SELECT * FROM users WHERE id = %s', user_id)"
    )  # noqa: print
    print("        return cursor.fetchone()")  # noqa: print
    print()  # noqa: print
    print("# ✅ Repository pattern")  # noqa: print
    print("class UserRepository(ABC):")  # noqa: print
    print("    @abstractmethod")  # noqa: print
    print("    def get_by_id(self, user_id: int) -> User: pass")  # noqa: print
    print("    ")  # noqa: print
    print("    @abstractmethod")  # noqa: print
    print("    def save(self, user: User): pass")  # noqa: print
    print()  # noqa: print
    print("class UserService:")  # noqa: print
    print("    def __init__(self, user_repo: UserRepository):")  # noqa: print
    print("        self.user_repo = user_repo")  # noqa: print
    print("    ")  # noqa: print
    print("    def get_user(self, user_id: int) -> User:")  # noqa: print
    print("        return self.user_repo.get_by_id(user_id)")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print


async def demonstrate_architecture_testing():
    """Show how to add architectural tests"""

    print("=== Architectural Testing Setup ===\n")  # noqa: print

    print("🧪 **Add Architectural Tests:**")  # noqa: print
    print()  # noqa: print

    print("**1. Dependency Rules Testing:**")  # noqa: print
    print("```python")  # noqa: print
    print("import ast")  # noqa: print
    print("from pathlib import Path")  # noqa: print
    print()  # noqa: print
    print("def test_layer_dependencies():")  # noqa: print
    print(
        '    """Test that presentation layer doesn\'t import from infrastructure"""'
    )  # noqa: print
    print(
        "    presentation_files = list(Path('src/presentation').glob('**/*.py'))"
    )  # noqa: print
    print("    ")  # noqa: print
    print("    for file_path in presentation_files:")  # noqa: print
    print("        with open(file_path) as f:")  # noqa: print
    print("            tree = ast.parse(f.read())")  # noqa: print
    print("        ")  # noqa: print
    print("        for node in ast.walk(tree):")  # noqa: print
    print("            if isinstance(node, ast.ImportFrom):")  # noqa: print
    print(
        "                if node.module and 'infrastructure' in node.module:"
    )  # noqa: print
    print(  # noqa: print
        "                    assert False, f'{file_path} imports from infrastructure'"
    )
    print("```")  # noqa: print
    print()  # noqa: print

    print("**2. Complexity Monitoring:**")  # noqa: print
    print("```python")  # noqa: print
    print("def test_class_complexity():")  # noqa: print
    print('    """Ensure classes don\'t exceed complexity thresholds"""')  # noqa: print
    print("    for file_path in Path('src').rglob('*.py'):")  # noqa: print
    print("        with open(file_path) as f:")  # noqa: print
    print("            tree = ast.parse(f.read())")  # noqa: print
    print("        ")  # noqa: print
    print("        for node in ast.walk(tree):")  # noqa: print
    print("            if isinstance(node, ast.ClassDef):")  # noqa: print
    print(  # noqa: print
        "                method_count = len([n for n in node.body if isinstance(n, ast.FunctionDef)])"
    )
    print(  # noqa: print
        "                assert method_count < 20, f'Class {node.name} has {method_count} methods'"
    )
    print("```")  # noqa: print
    print()  # noqa: print

    print("**3. Pattern Enforcement:**")  # noqa: print
    print("```python")  # noqa: print
    print("def test_singleton_pattern():")  # noqa: print
    print('    """Ensure singletons are properly implemented"""')  # noqa: print
    print("    singleton_files = find_singleton_classes()")  # noqa: print
    print("    ")  # noqa: print
    print("    for file_path, class_name in singleton_files:")  # noqa: print
    print("        # Verify __new__ method is implemented")  # noqa: print
    print("        # Verify thread safety")  # noqa: print
    print("        # Verify instance management")  # noqa: print
    print("        pass")  # noqa: print
    print("```")  # noqa: print
    print()  # noqa: print


async def main():
    """Run the architectural pattern analysis"""

    # Analyze architectural patterns
    await analyze_architectural_patterns()

    # Show architectural testing setup
    await demonstrate_architecture_testing()

    print("\n=== Analysis Complete ===")  # noqa: print
    print("Next steps:")  # noqa: print
    print(
        "1. Review architectural_analysis_report.json for detailed findings"
    )  # noqa: print
    print("2. Fix high-severity architectural issues first")  # noqa: print
    print("3. Reduce coupling in highly-coupled components")  # noqa: print
    print("4. Improve cohesion in low-cohesion classes")  # noqa: print
    print("5. Apply appropriate design patterns")  # noqa: print
    print("6. Add architectural tests to enforce design rules")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
