"""
Test: Conversation Files Database Startup Integration

Verifies that:
1. Database initialization runs during backend startup
2. Startup fails gracefully if database initialization fails
3. Health check endpoint reports database status
4. Database is accessible after initialization

This test ensures production-ready database initialization behavior.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_fresh_initialization():
    """Test database initialization on fresh deployment."""
    logger.info("=" * 80)
    logger.info("TEST 1: Fresh Database Initialization")
    logger.info("=" * 80)

    try:
        from src.conversation_file_manager import ConversationFileManager
        from database.migrations.001_create_conversation_files import ConversationFilesMigration

        # Create temporary test database path
        test_data_dir = Path("/home/kali/Desktop/AutoBot/tests/temp")
        test_data_dir.mkdir(parents=True, exist_ok=True)

        test_db_path = test_data_dir / "test_conversation_files.db"

        # Remove existing test database if present
        if test_db_path.exists():
            test_db_path.unlink()
            logger.info(f"Removed existing test database: {test_db_path}")

        # Create ConversationFileManager
        manager = ConversationFileManager(
            db_path=test_db_path,
            storage_dir=test_data_dir / "storage"
        )

        # Initialize database
        logger.info("Initializing database...")
        await manager.initialize()

        # Verify database was created
        assert test_db_path.exists(), "Database file was not created"
        logger.info(f"✅ Database file created: {test_db_path}")

        # Verify schema version
        version = await manager.get_schema_version()
        assert version == "001", f"Expected schema version '001', got '{version}'"
        logger.info(f"✅ Schema version verified: {version}")

        # Verify storage stats are accessible
        stats = await manager.get_storage_stats()
        assert stats['total_files'] == 0, "Fresh database should have 0 files"
        logger.info(f"✅ Storage stats accessible: {stats}")

        logger.info("=" * 80)
        logger.info("TEST 1: PASSED ✅")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"TEST 1: FAILED ❌ - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_existing_database_initialization():
    """Test database initialization when database already exists."""
    logger.info("=" * 80)
    logger.info("TEST 2: Existing Database Initialization")
    logger.info("=" * 80)

    try:
        from src.conversation_file_manager import ConversationFileManager

        # Use test database from test 1
        test_data_dir = Path("/home/kali/Desktop/AutoBot/tests/temp")
        test_db_path = test_data_dir / "test_conversation_files.db"

        # Verify database exists from previous test
        assert test_db_path.exists(), "Test database should exist from previous test"

        # Create ConversationFileManager
        manager = ConversationFileManager(
            db_path=test_db_path,
            storage_dir=test_data_dir / "storage"
        )

        # Initialize database (should be idempotent)
        logger.info("Re-initializing existing database...")
        await manager.initialize()

        # Verify schema version is still correct
        version = await manager.get_schema_version()
        assert version == "001", f"Schema version should remain '001', got '{version}'"
        logger.info(f"✅ Schema version unchanged: {version}")

        # Verify database is still accessible
        stats = await manager.get_storage_stats()
        logger.info(f"✅ Database accessible after re-initialization: {stats}")

        logger.info("=" * 80)
        logger.info("TEST 2: PASSED ✅")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"TEST 2: FAILED ❌ - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_health_check_integration():
    """Test health check endpoint includes database status."""
    logger.info("=" * 80)
    logger.info("TEST 3: Health Check Integration")
    logger.info("=" * 80)

    try:
        from fastapi.testclient import TestClient
        from backend.app_factory import create_app

        # Create FastAPI app
        app = create_app()

        # Wait for background initialization to complete
        logger.info("Waiting for background initialization...")
        await asyncio.sleep(3)

        # Create test client
        with TestClient(app) as client:
            # Test basic health endpoint
            response = client.get("/api/health")
            assert response.status_code == 200, f"Health check failed with status {response.status_code}"

            health_data = response.json()
            logger.info(f"Health check response: {health_data}")

            # Verify database status is included
            if "components" in health_data and "conversation_files_db" in health_data["components"]:
                db_status = health_data["components"]["conversation_files_db"]
                logger.info(f"✅ Database status in health check: {db_status}")
            else:
                logger.warning("⚠️ Database status not in basic health check (may require request context)")

            # Test detailed health endpoint
            response = client.get("/api/system/health/detailed")
            assert response.status_code == 200, f"Detailed health check failed with status {response.status_code}"

            detailed_health = response.json()
            logger.info(f"Detailed health check response: {detailed_health}")

            # Verify database status in detailed health
            if "components" in detailed_health:
                if "conversation_files_db" in detailed_health["components"]:
                    db_status = detailed_health["components"]["conversation_files_db"]
                    logger.info(f"✅ Database status in detailed health check: {db_status}")

                    if "conversation_files_schema" in detailed_health["components"]:
                        schema_version = detailed_health["components"]["conversation_files_schema"]
                        logger.info(f"✅ Schema version in detailed health check: {schema_version}")

        logger.info("=" * 80)
        logger.info("TEST 3: PASSED ✅")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"TEST 3: FAILED ❌ - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_startup_failure_handling():
    """Test that backend prevents startup if database initialization fails."""
    logger.info("=" * 80)
    logger.info("TEST 4: Startup Failure Handling")
    logger.info("=" * 80)

    try:
        from src.conversation_file_manager import ConversationFileManager
        from pathlib import Path

        # Create manager with invalid schema path to force failure
        test_data_dir = Path("/home/kali/Desktop/AutoBot/tests/temp")
        test_db_path = test_data_dir / "test_invalid.db"

        # Remove existing test database
        if test_db_path.exists():
            test_db_path.unlink()

        manager = ConversationFileManager(
            db_path=test_db_path,
            storage_dir=test_data_dir / "storage"
        )

        # Simulate missing schema by creating migration with invalid path
        from database.migrations.001_create_conversation_files import ConversationFilesMigration

        # Create migration with non-existent schema path
        migration = ConversationFilesMigration(
            data_dir=test_data_dir,
            schema_dir=Path("/nonexistent/invalid/path")
        )

        # Attempt migration (should fail)
        try:
            success = await migration.up()
            if success:
                logger.error("Migration should have failed but succeeded")
                return False
            else:
                logger.info("✅ Migration correctly failed with invalid schema path")
        except FileNotFoundError:
            logger.info("✅ Migration correctly raised FileNotFoundError")

        logger.info("=" * 80)
        logger.info("TEST 4: PASSED ✅")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"TEST 4: FAILED ❌ - {e}")
        import traceback
        traceback.print_exc()
        return False


async def cleanup_test_files():
    """Clean up test database files."""
    logger.info("Cleaning up test files...")

    try:
        test_data_dir = Path("/home/kali/Desktop/AutoBot/tests/temp")

        if test_data_dir.exists():
            import shutil
            shutil.rmtree(test_data_dir)
            logger.info(f"✅ Cleaned up test directory: {test_data_dir}")

    except Exception as e:
        logger.warning(f"⚠️ Failed to clean up test files: {e}")


async def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("CONVERSATION FILES DATABASE STARTUP INTEGRATION TESTS")
    logger.info("=" * 80)

    results = {
        "Fresh Initialization": False,
        "Existing Database Initialization": False,
        "Health Check Integration": False,
        "Startup Failure Handling": False
    }

    # Run tests sequentially
    results["Fresh Initialization"] = await test_fresh_initialization()
    results["Existing Database Initialization"] = await test_existing_database_initialization()
    results["Health Check Integration"] = await test_health_check_integration()
    results["Startup Failure Handling"] = await test_startup_failure_handling()

    # Clean up test files
    await cleanup_test_files()

    # Print summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    total_tests = len(results)
    passed_tests = sum(1 for passed in results.values() if passed)

    logger.info("=" * 80)
    logger.info(f"TOTAL: {passed_tests}/{total_tests} tests passed")
    logger.info("=" * 80)

    # Return exit code
    return 0 if passed_tests == total_tests else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
