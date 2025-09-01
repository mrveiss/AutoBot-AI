"""
MCP Manual Integration - System Manual and Help Lookup Service

Provides integration with MCP servers for looking up manual pages, help documentation,
and system command information. This is essential for terminal and system tasks.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MCPManualService:
    """
    Service for looking up system manuals and help information via MCP.
    
    Integrates with MCP servers to provide:
    - Linux manual pages (man pages)
    - Command help information (--help output)
    - System documentation
    - Tool usage instructions
    """
    
    def __init__(self):
        """Initialize the MCP manual service"""
        self.available_mcps = []
        self.command_cache = {}  # Cache for frequently requested commands
        self.cache_timeout = 300  # 5 minutes
        
        logger.info("MCPManualService initialized")
    
    async def lookup_manual(self, query: str, command: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Look up manual information for a query or specific command.
        
        Args:
            query: Search query or description
            command: Specific command to look up (optional)
            
        Returns:
            Dictionary with manual information or None if not found
        """
        try:
            # Extract command from query if not provided
            if not command:
                command = self._extract_command_from_query(query)
            
            if command:
                logger.info(f"Looking up manual for command: {command}")
                
                # Try different lookup strategies
                manual_info = await self._lookup_command_manual(command)
                if manual_info:
                    return manual_info
                
                # Try help lookup if manual not found
                help_info = await self._lookup_command_help(command)
                if help_info:
                    return help_info
            
            # General documentation search
            doc_info = await self._search_documentation(query)
            return doc_info
            
        except Exception as e:
            logger.error(f"Manual lookup failed for '{query}': {e}")
            return None
    
    def _extract_command_from_query(self, query: str) -> Optional[str]:
        """
        Extract command name from a natural language query.
        
        Args:
            query: Natural language query
            
        Returns:
            Extracted command name or None
        """
        # Common patterns for command extraction
        patterns = [
            r"how to use (\w+)",
            r"(\w+) command",
            r"run (\w+)",
            r"execute (\w+)",
            r"help with (\w+)",
            r"manual for (\w+)",
            r"documentation for (\w+)",
            r"(?:^|\s)(\w+)(?:\s|$)"  # Single word (last resort)
        ]
        
        query_lower = query.lower()
        
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                command = match.group(1)
                # Filter out common non-command words
                if command not in ['how', 'to', 'use', 'the', 'a', 'an', 'is', 'are', 'can', 'will', 'help', 'with']:
                    return command
        
        return None
    
    async def _lookup_command_manual(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Look up manual page for a specific command.
        
        Args:
            command: Command name to look up
            
        Returns:
            Manual page information or None
        """
        try:
            # Check cache first
            cache_key = f"man_{command}"
            if self._check_cache(cache_key):
                return self.command_cache[cache_key]['data']
            
            # TODO: Integrate with actual MCP server for manual pages
            # This would typically call an MCP server like context7 or similar
            
            # Placeholder implementation - would be replaced with actual MCP calls
            manual_data = await self._mock_manual_lookup(command)
            
            if manual_data:
                # Cache the result
                self._cache_result(cache_key, manual_data)
                return manual_data
            
            return None
            
        except Exception as e:
            logger.error(f"Manual lookup failed for command '{command}': {e}")
            return None
    
    async def _lookup_command_help(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Look up help information for a command (--help output).
        
        Args:
            command: Command name
            
        Returns:
            Help information or None
        """
        try:
            # Check cache first
            cache_key = f"help_{command}"
            if self._check_cache(cache_key):
                return self.command_cache[cache_key]['data']
            
            # TODO: Integrate with MCP server for command help
            # This would execute commands safely in a controlled environment
            
            # Placeholder implementation
            help_data = await self._mock_help_lookup(command)
            
            if help_data:
                # Cache the result
                self._cache_result(cache_key, help_data)
                return help_data
            
            return None
            
        except Exception as e:
            logger.error(f"Help lookup failed for command '{command}': {e}")
            return None
    
    async def _search_documentation(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search general documentation for a query.
        
        Args:
            query: Search query
            
        Returns:
            Documentation results or None
        """
        try:
            # TODO: Integrate with documentation MCP servers
            # This would search through system documentation, guides, etc.
            
            # Placeholder implementation
            doc_data = await self._mock_documentation_search(query)
            return doc_data
            
        except Exception as e:
            logger.error(f"Documentation search failed for '{query}': {e}")
            return None
    
    async def _mock_manual_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Mock manual lookup - replace with actual MCP integration.
        
        This is a placeholder that simulates manual page lookup.
        In production, this would integrate with actual MCP servers.
        """
        # Simulate some common commands
        mock_manuals = {
            'ls': {
                'name': 'ls',
                'section': '1',
                'description': 'list directory contents',
                'synopsis': 'ls [OPTION]... [FILE]...',
                'content': '''List information about the FILEs (the current directory by default).
                
OPTIONS:
    -l     use a long listing format
    -a     do not ignore entries starting with .
    -h     with -l, print sizes in human readable format
    -r     reverse order while sorting
    -t     sort by modification time
    
EXAMPLES:
    ls -la      List all files with details
    ls -lh      List with human-readable sizes
    ls -lt      List sorted by modification time''',
                'source': 'system_manual'
            },
            'grep': {
                'name': 'grep',
                'section': '1', 
                'description': 'search text using patterns',
                'synopsis': 'grep [OPTIONS] PATTERN [FILE...]',
                'content': '''Search for PATTERN in each FILE or standard input.
                
OPTIONS:
    -i     ignore case distinctions
    -r     read all files under each directory, recursively
    -n     prefix each line with line number
    -v     invert match (show non-matching lines)
    -c     print only a count of matching lines
    
EXAMPLES:
    grep "pattern" file.txt     Search for pattern in file
    grep -i "pattern" file.txt  Case-insensitive search
    grep -r "pattern" dir/      Recursive search in directory''',
                'source': 'system_manual'
            }
        }
        
        if command in mock_manuals:
            return mock_manuals[command]
        
        return None
    
    async def _mock_help_lookup(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Mock help lookup - replace with actual command execution via MCP.
        """
        # Simulate help output for common commands
        mock_help = {
            'curl': {
                'name': 'curl',
                'description': 'transfer data from or to a server',
                'content': '''Usage: curl [options...] <url>
                
Options:
    -X, --request <command>     Specify request command to use
    -H, --header <header>       Pass custom header to server
    -d, --data <data>           HTTP POST data
    -o, --output <file>         Write output to file
    -s, --silent                Silent mode
    -v, --verbose               Make the operation more talkative
    
Examples:
    curl https://example.com
    curl -X POST -d "data" https://api.example.com''',
                'source': 'command_help'
            }
        }
        
        if command in mock_help:
            return mock_help[command]
        
        return None
    
    async def _mock_documentation_search(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Mock documentation search - replace with actual documentation MCP integration.
        """
        # This would search through system documentation
        return {
            'query': query,
            'results': [
                {
                    'title': f'Documentation for: {query}',
                    'content': f'Found documentation related to: {query}. This would contain actual documentation content from system docs.',
                    'source': 'system_documentation',
                    'relevance': 0.8
                }
            ]
        }
    
    def _check_cache(self, cache_key: str) -> bool:
        """Check if cached result is still valid"""
        import time
        
        if cache_key in self.command_cache:
            cache_entry = self.command_cache[cache_key]
            if time.time() - cache_entry['timestamp'] < self.cache_timeout:
                return True
            else:
                # Remove expired cache entry
                del self.command_cache[cache_key]
        
        return False
    
    def _cache_result(self, cache_key: str, data: Dict[str, Any]):
        """Cache lookup result"""
        import time
        
        self.command_cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        # Limit cache size
        if len(self.command_cache) > 100:
            # Remove oldest entries
            sorted_keys = sorted(
                self.command_cache.keys(),
                key=lambda k: self.command_cache[k]['timestamp']
            )
            for key in sorted_keys[:20]:  # Remove oldest 20 entries
                del self.command_cache[key]


# Global service instance
mcp_manual_service = MCPManualService()


async def lookup_system_manual(query: str, command: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Convenience function to look up system manual information.
    
    Args:
        query: Search query or description
        command: Specific command to look up (optional)
        
    Returns:
        Manual information or None if not found
    """
    return await mcp_manual_service.lookup_manual(query, command)


async def get_command_help(command: str) -> Optional[str]:
    """
    Get help information for a specific command.
    
    Args:
        command: Command name
        
    Returns:
        Help text or None if not found
    """
    result = await mcp_manual_service._lookup_command_help(command)
    if result:
        return result.get('content', '')
    return None


async def search_system_documentation(query: str) -> List[Dict[str, Any]]:
    """
    Search system documentation for a query.
    
    Args:
        query: Search query
        
    Returns:
        List of documentation results
    """
    result = await mcp_manual_service._search_documentation(query)
    if result and 'results' in result:
        return result['results']
    return []