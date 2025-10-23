#!/usr/bin/env python3
"""
Test script for the comprehensive system validation
"""

import asyncio
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_system_validation():
    """Test the system validation directly"""
    logger.info("🧪 Testing System Validation")
    
    try:
        from src.utils.system_validator import get_system_validator
        
        # Initialize validator
        validator = get_system_validator()
        logger.info("✅ System validator initialized")
        
        # Run quick validation of each component
        logger.info("🔍 Running component validations...")
        
        # Test cache validation
        cache_results = await validator.validate_knowledge_base_caching()
        cache_success = all(r.status for r in cache_results) if cache_results else False
        logger.info(f"Cache Validation: {'✅ PASSED' if cache_success else '❌ FAILED'} ({len(cache_results)} checks)")
        
        # Test search validation  
        search_results = await validator.validate_hybrid_search()
        search_success = all(r.status for r in search_results) if search_results else False
        logger.info(f"Search Validation: {'✅ PASSED' if search_success else '❌ FAILED'} ({len(search_results)} checks)")
        
        # Test monitoring validation
        monitoring_results = await validator.validate_monitoring_system()
        monitoring_success = all(r.status for r in monitoring_results) if monitoring_results else False
        logger.info(f"Monitoring Validation: {'✅ PASSED' if monitoring_success else '❌ FAILED'} ({len(monitoring_results)} checks)")
        
        # Test model optimization validation
        model_results = await validator.validate_model_optimization()
        model_success = all(r.status for r in model_results) if model_results else False
        logger.info(f"Model Optimization: {'✅ PASSED' if model_success else '❌ FAILED'} ({len(model_results)} checks)")
        
        # Run comprehensive validation
        logger.info("🚀 Running comprehensive validation...")
        comprehensive_result = await validator.run_comprehensive_validation()
        
        # comprehensive_result is a SystemValidationReport object
        success = comprehensive_result.passed_tests > comprehensive_result.failed_tests
        
        if success:
            logger.info(f"🎉 COMPREHENSIVE VALIDATION PASSED!")
        else:
            logger.info(f"⚠️ COMPREHENSIVE VALIDATION NEEDS ATTENTION")
            
        logger.info(f"Overall Results:")
        logger.info(f"  - Total Tests: {comprehensive_result.total_tests}")
        logger.info(f"  - Passed: {comprehensive_result.passed_tests}")
        logger.info(f"  - Failed: {comprehensive_result.failed_tests}")
        logger.info(f"  - Critical Issues: {comprehensive_result.critical_issues}")
        logger.info(f"  - Warnings: {comprehensive_result.warnings}")
        logger.info(f"  - Health Score: {comprehensive_result.health_score:.1f}%")
        logger.info(f"  - Production Ready: {comprehensive_result.production_ready}")
        
        if hasattr(comprehensive_result, 'recommendations') and comprehensive_result.recommendations:
            logger.info(f"Top Recommendations:")
            for rec in comprehensive_result.recommendations[:3]:
                logger.info(f"  - {rec}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ System validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    logger.info("🚀 System Validation Test Suite")
    
    success = await test_system_validation()
    
    if success:
        logger.info("✅ System validation test PASSED - System is ready for production!")
    else:
        logger.error("❌ System validation test FAILED - Issues need to be resolved")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())