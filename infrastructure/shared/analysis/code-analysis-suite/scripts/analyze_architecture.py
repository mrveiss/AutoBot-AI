#!/usr/bin/env python3
"""
Analyze AutoBot codebase for architectural patterns and design quality
"""

import asyncio
import json
from pathlib import Path

from src.architectural_pattern_analyzer import ArchitecturalPatternAnalyzer
import logging



logger = logging.getLogger(__name__)

async def _display_summary_and_metrics(results):
    """Display summary and architectural quality metrics.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    logger.info("\n=== Architectural Pattern Analysis Results ===\n")

    # Summary
    logger.info(f"📊 **Analysis Summary:**")
    logger.info(f"   - Total components: {results['total_components']}")
    logger.info(f"   - Architectural issues: {results['architectural_issues']}")
    logger.info(f"   - Design patterns found: {results['design_patterns_found']}")
    logger.info(f"   - Architecture score: {results['architecture_score']}/100")
    logger.info(f"   - Analysis time: {results['analysis_time_seconds']:.2f}s\n")

    # Detailed metrics
    metrics = results["metrics"]
    logger.info("🏛️ **Architectural Quality Metrics:**")
    logger.info(
        f"   - Coupling score: {metrics['coupling_score']}/100 (lower coupling is better)"
    )
    logger.info(f"   - Cohesion score: {metrics['cohesion_score']}/100")
    logger.info(f"   - Pattern adherence: {metrics['pattern_adherence_score']}/100")
    logger.info(f"   - Maintainability index: {metrics['maintainability_index']}/100")
    logger.info(f"   - Abstraction score: {metrics['abstraction_score']}/100")
    logger.info(f"   - Instability score: {metrics['instability_score']}/100")
    logger.info()


async def _display_component_breakdown(results):
    """Display component breakdown by type.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    component_types = {}
    for comp in results["components"]:
        comp_type = comp["type"]
        component_types[comp_type] = component_types.get(comp_type, 0) + 1

    logger.info("🧩 **Component Breakdown:**")
    for comp_type, count in component_types.items():
        logger.info(f"   - {comp_type.title()}s: {count}")
    logger.info()


async def _display_design_patterns(results):
    """Display detected design patterns.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    if results["detected_patterns"]:
        pattern_counts = {}
        for pattern in results["detected_patterns"]:
            pattern_name = pattern["pattern"]
            pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1

        logger.info("🎨 **Design Patterns Detected:**")
        for pattern, count in sorted(pattern_counts.items()):
            logger.info(f"   - {pattern.replace('_', ' ').title()}: {count} instances")

        logger.info("\n📋 **Pattern Details:**")
        for pattern in results["detected_patterns"][:10]:  # Show first 10
            logger.info(
                f"   - {pattern['pattern'].title()} in {pattern['file']}:{pattern['line']}"
            )
            logger.info(f"     {pattern['description']}")
        logger.info()


async def _display_architectural_issues(results):
    """Display architectural issues with severity.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    if results["architectural_issues"]:
        logger.info("🚨 **Architectural Issues:**")
        for issue in results["architectural_issues"]:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = severity_emoji.get(issue["severity"], "⚪")

            logger.info(
                f"\n   {emoji} **{issue['type'].replace('_', ' ').title()}** ({issue['severity']})"
            )
            logger.info(f"      {issue['description']}")
            logger.info(f"      Affects: {issue['affected_components_count']} components")
            logger.info(f"      💡 Suggestion: {issue['suggestion']}")
            logger.info(f"      🔧 Refactoring effort: {issue['refactoring_effort']}")
            if issue["pattern_violation"]:
                logger.info(f"      ❌ Violates: {issue['pattern_violation']}")


async def _display_coupling_analysis(results):
    """Display high coupling analysis.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    high_coupling_components = [
        c for c in results["components"] if c["coupling_score"] > 10
    ]
    if high_coupling_components:
        logger.info(f"\n🔗 **High Coupling Analysis:**")
        logger.info(
            f"   Found {len(high_coupling_components)} components with high coupling:"
        )
        for comp in high_coupling_components[:5]:  # Show top 5
            logger.info(f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}")
            logger.info(f"     Coupling score: {comp['coupling_score']} dependencies")
            logger.info(f"     Dependencies: {', '.join(comp['dependencies'][:5])}")
            if len(comp["dependencies"]) > 5:
                logger.info(f"     ... and {len(comp['dependencies']) - 5} more")
        logger.info()


async def _display_cohesion_and_complexity(results):
    """Display low cohesion and high complexity analysis.

    Helper for analyze_architectural_patterns (Issue #825).
    """
    # Low cohesion analysis
    low_cohesion_classes = [
        c
        for c in results["components"]
        if c["type"] == "class" and c["cohesion_score"] < 0.3
    ]
    if low_cohesion_classes:
        logger.info(f"🔄 **Low Cohesion Analysis:**")
        logger.info(f"   Found {len(low_cohesion_classes)} classes with low cohesion:")
        for comp in low_cohesion_classes[:5]:
            logger.info(f"   - Class '{comp['name']}' in {comp['file']}")
            logger.info(f"     Cohesion score: {comp['cohesion_score']:.2f}")
            logger.info(f"     Interfaces: {len(comp['interfaces'])} methods")
        logger.info()

    # Complex components
    complex_components = [
        c for c in results["components"] if c["complexity_score"] > 20
    ]
    if complex_components:
        logger.info(f"🧠 **High Complexity Analysis:**")
        logger.info(f"   Found {len(complex_components)} highly complex components:")
        for comp in complex_components[:5]:
            logger.info(f"   - {comp['type'].title()} '{comp['name']}' in {comp['file']}")
            logger.info(f"     Complexity score: {comp['complexity_score']}")
            if comp["patterns"]:
                logger.info(f"     Patterns: {', '.join(comp['patterns'])}")
        logger.info()


async def analyze_architectural_patterns():
    """Analyze codebase for architectural patterns and design issues"""

    logger.info("🏗️ Starting architectural pattern analysis...")

    analyzer = ArchitecturalPatternAnalyzer()

    # Run analysis
    results = await analyzer.analyze_architecture(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    await _display_summary_and_metrics(results)
    await _display_component_breakdown(results)
    await _display_design_patterns(results)
    await _display_architectural_issues(results)
    await _display_coupling_analysis(results)
    await _display_cohesion_and_complexity(results)

    # Save detailed report
    report_path = Path("architectural_analysis_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"📋 Detailed report saved to: {report_path}")

    # Generate architecture recommendations
    await generate_architecture_recommendations(results)

    return results


async def _dependency_injection():
    """Display Dependency Injection.

    Helper for generate_architecture_recommendations (Issue #825).
    """
    # Dependency Injection
    logger.info("**2. Dependency Injection Pattern:**")
    logger.info("```python")
    logger.info("# ❌ Tight coupling")
    logger.info("class OrderService:")
    logger.info("    def __init__(self):")
    logger.info("        self.db = MySQLDatabase()  # Hard dependency")
    logger.info("        self.email = SMTPEmailService()  # Hard dependency")
    logger.info()
    logger.info("# ✅ Dependency injection")
    logger.info("from abc import ABC, abstractmethod")
    logger.info()
    logger.info("class DatabaseInterface(ABC):")
    logger.info("    @abstractmethod")
    logger.info("    def save(self, data): pass")
    logger.info()
    logger.info("class OrderService:")
    logger.info("    def __init__(self, db: DatabaseInterface, email_service):")
    logger.info("        self.db = db  # Injected dependency")
    logger.info("        self.email = email_service  # Injected dependency")
    logger.info("```")
    logger.info()


async def _observer_pattern():
    """Display Observer Pattern.

    Helper for generate_architecture_recommendations (Issue #825).
    """
    # Observer Pattern
    logger.info("**3. Observer Pattern for Event Handling:**")
    logger.info("```python")
    logger.info("# ❌ Tight coupling between components")
    logger.info("class User:")
    logger.info("    def update_profile(self):")
    logger.info("        # Direct calls to other services")
    logger.info("        email_service.send_notification()")
    logger.info("        audit_service.log_change()")
    logger.info("        cache_service.invalidate()")
    logger.info()
    logger.info("# ✅ Observer pattern")
    logger.info("class EventBus:")
    logger.info("    def __init__(self):")
    logger.info("        self.observers = []")
    logger.info("    ")
    logger.info("    def subscribe(self, observer):")
    logger.info("        self.observers.append(observer)")
    logger.info("    ")
    logger.info("    def notify(self, event):")
    logger.info("        for observer in self.observers:")
    logger.info("            observer.handle(event)")
    logger.info()
    logger.info("class User:")
    logger.info("    def update_profile(self):")
    logger.info("        # Publish event instead of direct coupling")
    logger.info("        event_bus.notify(ProfileUpdatedEvent(self))")
    logger.info("```")
    logger.info()


async def _factory_pattern(config_type):
    """Display Factory Pattern.

    Helper for generate_architecture_recommendations (Issue #825).
    """
    # Factory Pattern
    logger.info("**4. Factory Pattern for Object Creation:**")
    logger.info("```python")
    logger.info("# ❌ Complex object creation scattered everywhere")
    logger.info("if config_type == 'development':")
    logger.info("    db = SqliteDatabase()")
    logger.info("elif config_type == 'production':")
    logger.info("    db = PostgresDatabase()")
    logger.info()
    logger.info("# ✅ Factory pattern")
    logger.info("class DatabaseFactory:")
    logger.info("    @staticmethod")
    logger.info("    def create_database(config_type: str):")
    logger.info("        if config_type == 'development':")
    logger.info("            return SqliteDatabase()")
    logger.info("        elif config_type == 'production':")
    logger.info("            return PostgresDatabase()")
    logger.info("        else:")
    logger.info("            raise ValueError(f'Unknown config type: {config_type}')")
    logger.info("```")
    logger.info()

    # Layered Architecture
    logger.info("**5. Layered Architecture Pattern:**")
    logger.info("```")
    logger.info("src/")
    logger.info("├── presentation/     # Controllers, API endpoints")
    logger.info("├── application/      # Use cases, application services")
    logger.info("├── domain/          # Business logic, entities")
    logger.info("└── infrastructure/  # Database, external services")
    logger.info()
    logger.info("# Dependency flow: Presentation -> Application -> Domain")
    logger.info("# Infrastructure depends on Domain (Dependency Inversion)")
    logger.info("```")
    logger.info()


async def _repository_pattern():
    """Display Repository Pattern.

    Helper for generate_architecture_recommendations (Issue #825).
    """
    # Repository Pattern
    logger.info("**6. Repository Pattern for Data Access:**")
    logger.info("```python")
    logger.info("# ❌ Direct database calls in business logic")
    logger.info("class UserService:")
    logger.info("    def get_user(self, user_id):")
    logger.info("        cursor.execute('SELECT * FROM users WHERE id = %s', user_id)")
    logger.info("        return cursor.fetchone()")
    logger.info()
    logger.info("# ✅ Repository pattern")
    logger.info("class UserRepository(ABC):")
    logger.info("    @abstractmethod")
    logger.info("    def get_by_id(self, user_id: int) -> User: pass")
    logger.info("    ")
    logger.info("    @abstractmethod")
    logger.info("    def save(self, user: User): pass")
    logger.info()
    logger.info("class UserService:")
    logger.info("    def __init__(self, user_repo: UserRepository):")
    logger.info("        self.user_repo = user_repo")
    logger.info("    ")
    logger.info("    def get_user(self, user_id: int) -> User:")
    logger.info("        return self.user_repo.get_by_id(user_id)")
    logger.info("```")
    logger.info()


async def generate_architecture_recommendations(results):
    """Generate specific architectural improvement recommendations"""

    logger.info("\n=== Architectural Improvement Recommendations ===\n")

    recommendations = results["recommendations"]

    if recommendations:
        logger.info("🏗️ **Priority Recommendations:**")
        for i, rec in enumerate(recommendations, 1):
            logger.info(f"{i}. {rec}")
        logger.info()

    # Specific improvement patterns
    logger.info("🛠️ **Architectural Improvement Patterns:**\n")

    # SOLID Principles
    logger.info("**1. SOLID Principles Application:**")
    logger.info("```python")
    logger.info("# ❌ God class violating SRP")
    logger.info("class UserManager:")
    logger.info("    def create_user(self): pass")
    logger.info("    def send_email(self): pass")
    logger.info("    def log_action(self): pass")
    logger.info("    def validate_data(self): pass")
    logger.info()
    logger.info("# ✅ Separated responsibilities")
    logger.info("class UserService:")
    logger.info("    def create_user(self): pass")
    logger.info()
    logger.info("class EmailService:")
    logger.info("    def send_email(self): pass")
    logger.info()
    logger.info("class Logger:")
    logger.info("    def log_action(self): pass")
    logger.info()
    logger.info("class Validator:")
    logger.info("    def validate_data(self): pass")
    logger.info("```")
    logger.info()

    await _dependency_injection()


    await _observer_pattern()


    await _factory_pattern(config_type)


    await _repository_pattern()



async def demonstrate_architecture_testing():
    """Show how to add architectural tests"""

    logger.info("=== Architectural Testing Setup ===\n")

    logger.info("🧪 **Add Architectural Tests:**")
    logger.info()

    logger.info("**1. Dependency Rules Testing:**")
    logger.info("```python")
    logger.info("import ast")
    logger.info("from pathlib import Path")
    logger.info()
    logger.info("def test_layer_dependencies():")
    logger.info('    """Test that presentation layer doesn\'t import from infrastructure"""')
    logger.info("    presentation_files = list(Path('src/presentation').glob('**/*.py'))")
    logger.info("    ")
    logger.info("    for file_path in presentation_files:")
    logger.info("        with open(file_path) as f:")
    logger.info("            tree = ast.parse(f.read())")
    logger.info("        ")
    logger.info("        for node in ast.walk(tree):")
    logger.info("            if isinstance(node, ast.ImportFrom):")
    logger.info("                if node.module and 'infrastructure' in node.module:")
    logger.info(
        "                    assert False, f'{file_path} imports from infrastructure'"
    )
    logger.info("```")
    logger.info()

    logger.info("**2. Complexity Monitoring:**")
    logger.info("```python")
    logger.info("def test_class_complexity():")
    logger.info('    """Ensure classes don\'t exceed complexity thresholds"""')
    logger.info("    for file_path in Path('src').rglob('*.py'):")
    logger.info("        with open(file_path) as f:")
    logger.info("            tree = ast.parse(f.read())")
    logger.info("        ")
    logger.info("        for node in ast.walk(tree):")
    logger.info("            if isinstance(node, ast.ClassDef):")
    logger.info(
        "                method_count = len([n for n in node.body if isinstance(n, ast.FunctionDef)])"
    )
    logger.info(
        "                assert method_count < 20, f'Class {node.name} has {method_count} methods'"
    )
    logger.info("```")
    logger.info()

    logger.info("**3. Pattern Enforcement:**")
    logger.info("```python")
    logger.info("def test_singleton_pattern():")
    logger.info('    """Ensure singletons are properly implemented"""')
    logger.info("    singleton_files = find_singleton_classes()")
    logger.info("    ")
    logger.info("    for file_path, class_name in singleton_files:")
    logger.info("        # Verify __new__ method is implemented")
    logger.info("        # Verify thread safety")
    logger.info("        # Verify instance management")
    logger.info("        pass")
    logger.info("```")
    logger.info()


async def main():
    """Run the architectural pattern analysis"""

    # Analyze architectural patterns
    await analyze_architectural_patterns()

    # Show architectural testing setup
    await demonstrate_architecture_testing()

    logger.info("\n=== Analysis Complete ===")
    logger.info("Next steps:")
    logger.info("1. Review architectural_analysis_report.json for detailed findings")
    logger.info("2. Fix high-severity architectural issues first")
    logger.info("3. Reduce coupling in highly-coupled components")
    logger.info("4. Improve cohesion in low-cohesion classes")
    logger.info("5. Apply appropriate design patterns")
    logger.info("6. Add architectural tests to enforce design rules")


if __name__ == "__main__":
    asyncio.run(main())
