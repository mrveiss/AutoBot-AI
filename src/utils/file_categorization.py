# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File categorization utility for codebase analysis tools.

Provides consistent file type detection and categorization across all
AutoBot code analysis features. Supports multiple programming languages,
frameworks, and file types.
"""

from pathlib import Path
from typing import Dict, Set

# =============================================================================
# File Categories
# =============================================================================

FILE_CATEGORY_CODE = "code"
FILE_CATEGORY_DOCS = "docs"
FILE_CATEGORY_LOGS = "logs"
FILE_CATEGORY_BACKUP = "backup"
FILE_CATEGORY_ARCHIVE = "archive"
FILE_CATEGORY_CONFIG = "config"
FILE_CATEGORY_DATA = "data"
FILE_CATEGORY_ASSETS = "assets"
FILE_CATEGORY_TEST = "test"

# Issue #665: Category display info extracted to module-level constant
_CATEGORY_INFO: Dict[str, Dict] = {
    FILE_CATEGORY_CODE: {
        "emoji": "📄",
        "title": "Code Files",
        "description": "Source code files",
        "priority": True,
        "count_metrics": True,
    },
    FILE_CATEGORY_CONFIG: {
        "emoji": "⚙️",
        "title": "Configuration",
        "description": "Configuration files",
        "priority": True,
        "count_metrics": True,
    },
    FILE_CATEGORY_TEST: {
        "emoji": "🧪",
        "title": "Test Files",
        "description": "Test and spec files",
        "priority": True,
        "count_metrics": True,
    },
    FILE_CATEGORY_DOCS: {
        "emoji": "📝",
        "title": "Documentation",
        "description": "Documentation files",
        "priority": False,
        "count_metrics": False,
    },
    FILE_CATEGORY_LOGS: {
        "emoji": "📋",
        "title": "Log Files",
        "description": "Log and output files",
        "priority": False,
        "count_metrics": False,
    },
    FILE_CATEGORY_BACKUP: {
        "emoji": "📦",
        "title": "Backup Files",
        "description": "Backup files for rollback",
        "priority": False,
        "count_metrics": False,
    },
    FILE_CATEGORY_ARCHIVE: {
        "emoji": "🗄️",
        "title": "Archived Files",
        "description": "Archived/deprecated files",
        "priority": False,
        "count_metrics": False,
    },
    FILE_CATEGORY_DATA: {
        "emoji": "📊",
        "title": "Data Files",
        "description": "Data and dataset files",
        "priority": False,
        "count_metrics": False,
    },
    FILE_CATEGORY_ASSETS: {
        "emoji": "🖼️",
        "title": "Asset Files",
        "description": "Images, fonts, media",
        "priority": False,
        "count_metrics": False,
    },
}

_DEFAULT_CATEGORY_INFO: Dict = {
    "emoji": "❓",
    "title": "Unknown",
    "description": "Unknown file type",
    "priority": False,
    "count_metrics": False,
}

# =============================================================================
# Programming Language Extensions
# =============================================================================

# Python
PYTHON_EXTENSIONS: Set[str] = {".py", ".pyw", ".pyi", ".pyx", ".pxd"}

# JavaScript / TypeScript
JS_EXTENSIONS: Set[str] = {".js", ".mjs", ".cjs", ".jsx"}
TS_EXTENSIONS: Set[str] = {".ts", ".mts", ".cts", ".tsx"}

# Web Frontend
VUE_EXTENSIONS: Set[str] = {".vue"}
CSS_EXTENSIONS: Set[str] = {".css", ".scss", ".sass", ".less", ".styl", ".stylus"}
HTML_EXTENSIONS: Set[str] = {".html", ".htm", ".xhtml", ".shtml"}
SVELTE_EXTENSIONS: Set[str] = {".svelte"}
ASTRO_EXTENSIONS: Set[str] = {".astro"}

# Backend / Systems
RUST_EXTENSIONS: Set[str] = {".rs"}
GO_EXTENSIONS: Set[str] = {".go"}
JAVA_EXTENSIONS: Set[str] = {".java"}
KOTLIN_EXTENSIONS: Set[str] = {".kt", ".kts"}
SCALA_EXTENSIONS: Set[str] = {".scala", ".sc"}
CSHARP_EXTENSIONS: Set[str] = {".cs", ".csx"}
CPP_EXTENSIONS: Set[str] = {
    ".cpp",
    ".cc",
    ".cxx",
    ".c++",
    ".hpp",
    ".hh",
    ".hxx",
    ".h++",
    ".h",
    ".c",
}
SWIFT_EXTENSIONS: Set[str] = {".swift"}
RUBY_EXTENSIONS: Set[str] = {".rb", ".rake", ".gemspec"}
PHP_EXTENSIONS: Set[str] = {
    ".php",
    ".phtml",
    ".php3",
    ".php4",
    ".php5",
    ".php7",
    ".phps",
}
PERL_EXTENSIONS: Set[str] = {".pl", ".pm", ".pod", ".t"}

# Shell / Scripting
SHELL_EXTENSIONS: Set[str] = {".sh", ".bash", ".zsh", ".fish", ".ksh", ".csh", ".tcsh"}
POWERSHELL_EXTENSIONS: Set[str] = {".ps1", ".psm1", ".psd1"}
BAT_EXTENSIONS: Set[str] = {".bat", ".cmd"}

# Data / Query Languages
SQL_EXTENSIONS: Set[str] = {".sql", ".psql", ".plsql", ".pgsql"}
GRAPHQL_EXTENSIONS: Set[str] = {".graphql", ".gql"}

# Mobile
DART_EXTENSIONS: Set[str] = {".dart"}
OBJECTIVE_C_EXTENSIONS: Set[str] = {".m", ".mm"}

# Functional
ELIXIR_EXTENSIONS: Set[str] = {".ex", ".exs"}
ERLANG_EXTENSIONS: Set[str] = {".erl", ".hrl"}
HASKELL_EXTENSIONS: Set[str] = {".hs", ".lhs"}
CLOJURE_EXTENSIONS: Set[str] = {".clj", ".cljs", ".cljc", ".edn"}
FSharp_EXTENSIONS: Set[str] = {".fs", ".fsi", ".fsx"}
LISP_EXTENSIONS: Set[str] = {".lisp", ".lsp", ".cl", ".fasl"}
SCHEME_EXTENSIONS: Set[str] = {".scm", ".ss"}
OCAML_EXTENSIONS: Set[str] = {".ml", ".mli"}

# Other
LUA_EXTENSIONS: Set[str] = {".lua"}
R_EXTENSIONS: Set[str] = {".r", ".R", ".rmd", ".Rmd"}
JULIA_EXTENSIONS: Set[str] = {".jl"}
NIM_EXTENSIONS: Set[str] = {".nim", ".nims"}
ZIG_EXTENSIONS: Set[str] = {".zig"}
V_EXTENSIONS: Set[str] = {".v"}
CRYSTAL_EXTENSIONS: Set[str] = {".cr"}
D_EXTENSIONS: Set[str] = {".d"}
FORTRAN_EXTENSIONS: Set[str] = {".f", ".f90", ".f95", ".f03", ".f08", ".for"}
COBOL_EXTENSIONS: Set[str] = {".cob", ".cbl", ".cobol"}
ASSEMBLY_EXTENSIONS: Set[str] = {".asm", ".s", ".S"}

# Combined: All code extensions
ALL_CODE_EXTENSIONS: Set[str] = (
    PYTHON_EXTENSIONS
    | JS_EXTENSIONS
    | TS_EXTENSIONS
    | VUE_EXTENSIONS
    | CSS_EXTENSIONS
    | HTML_EXTENSIONS
    | SVELTE_EXTENSIONS
    | ASTRO_EXTENSIONS
    | RUST_EXTENSIONS
    | GO_EXTENSIONS
    | JAVA_EXTENSIONS
    | KOTLIN_EXTENSIONS
    | SCALA_EXTENSIONS
    | CSHARP_EXTENSIONS
    | CPP_EXTENSIONS
    | SWIFT_EXTENSIONS
    | RUBY_EXTENSIONS
    | PHP_EXTENSIONS
    | PERL_EXTENSIONS
    | SHELL_EXTENSIONS
    | POWERSHELL_EXTENSIONS
    | BAT_EXTENSIONS
    | SQL_EXTENSIONS
    | GRAPHQL_EXTENSIONS
    | DART_EXTENSIONS
    | OBJECTIVE_C_EXTENSIONS
    | ELIXIR_EXTENSIONS
    | ERLANG_EXTENSIONS
    | HASKELL_EXTENSIONS
    | CLOJURE_EXTENSIONS
    | FSharp_EXTENSIONS
    | LISP_EXTENSIONS
    | SCHEME_EXTENSIONS
    | OCAML_EXTENSIONS
    | LUA_EXTENSIONS
    | R_EXTENSIONS
    | JULIA_EXTENSIONS
    | NIM_EXTENSIONS
    | ZIG_EXTENSIONS
    | V_EXTENSIONS
    | CRYSTAL_EXTENSIONS
    | D_EXTENSIONS
    | FORTRAN_EXTENSIONS
    | COBOL_EXTENSIONS
    | ASSEMBLY_EXTENSIONS
)

# =============================================================================
# Non-Code File Extensions
# =============================================================================

# Configuration files
CONFIG_EXTENSIONS: Set[str] = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".cfg",
    ".env",
    ".properties",
    ".xml",
    ".plist",
    ".editorconfig",
    ".eslintrc",
    ".prettierrc",
    ".babelrc",
    ".npmrc",
    ".yarnrc",
}

# Documentation files
DOC_EXTENSIONS: Set[str] = {
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".adoc",
    ".asciidoc",
    ".org",
    ".tex",
    ".latex",
    ".rtf",
    ".doc",
    ".docx",
    ".odt",
}

# Log files
LOG_EXTENSIONS: Set[str] = {
    ".log",
    ".log.1",
    ".log.2",
    ".log.gz",
    ".log.bak",
    ".logs",
    ".out",
    ".err",
}

# Data files
DATA_EXTENSIONS: Set[str] = {
    ".csv",
    ".tsv",
    ".parquet",
    ".avro",
    ".jsonl",
    ".ndjson",
    ".pickle",
    ".pkl",
    ".feather",
    ".hdf5",
    ".h5",
}

# Asset files (images, fonts, media)
ASSET_EXTENSIONS: Set[str] = {
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".psd",
    ".ai",
    ".eps",
    # Fonts
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    # Audio/Video
    ".mp3",
    ".wav",
    ".ogg",
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    # Other
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
}

# =============================================================================
# Directory Categories
# =============================================================================

# Directories to completely skip (no analysis value)
SKIP_DIRS: Set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".venv",
    "venv",
    ".DS_Store",
    "temp",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".cache",
    ".parcel-cache",
    "coverage",
    ".nyc_output",
    "htmlcov",
    ".tox",
    ".idea",
    ".vscode",
    ".vs",
    "vendor",
    "bower_components",
    "target",  # Rust/Java build output
    "bin",
    "obj",  # .NET build output
    ".gradle",
    ".m2",  # Java build caches
}

# Directory-based categories (not skipped, but categorized)
BACKUP_DIRS: Set[str] = {"backup", "backups", "bak", ".backup"}
ARCHIVE_DIRS: Set[str] = {
    "archive",
    "archives",
    "archived",
    "old",
    "deprecated",
    "legacy",
}
LOG_DIRS: Set[str] = {"logs", "log"}
TEST_DIRS: Set[str] = {
    "tests",
    "test",
    "__tests__",
    "spec",
    "specs",
    "e2e",
    "integration",
}
DOC_DIRS: Set[str] = {"docs", "doc", "documentation", "wiki"}
ASSET_DIRS: Set[str] = {"assets", "static", "public", "media", "images", "img", "fonts"}

# =============================================================================
# Language Detection
# =============================================================================

# Map extensions to language names
EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".pyx": "python",
    # JavaScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    # TypeScript
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    # Web
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    # Backend
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    # Shell
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    # Data
    ".sql": "sql",
    ".graphql": "graphql",
    # Mobile
    ".dart": "dart",
    ".m": "objective-c",
    # Functional
    ".ex": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".clj": "clojure",
    ".fs": "fsharp",
    ".ml": "ocaml",
    # Other
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
    ".nim": "nim",
    ".zig": "zig",
    ".cr": "crystal",
    # Config
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".ini": "ini",
    # Docs
    ".md": "markdown",
    ".rst": "restructuredtext",
}


# =============================================================================
# Core Functions
# =============================================================================


def get_file_category(file_path: Path) -> str:
    """
    Determine the category of a file based on its path and extension.

    Categories:
    - code: Programming language source files
    - config: Configuration files
    - docs: Documentation files
    - logs: Log files
    - backup: Files in backup directories
    - archive: Files in archive/deprecated directories
    - test: Test files and directories
    - data: Data files (CSV, Parquet, etc.)
    - assets: Images, fonts, media files

    Args:
        file_path: Path object for the file

    Returns:
        Category string for proper tracking and reporting.
    """
    path_parts = set(p.lower() for p in file_path.parts)
    extension = file_path.suffix.lower()
    filename = file_path.name.lower()

    # Check directory-based categories first (takes precedence)
    if path_parts & BACKUP_DIRS:
        return FILE_CATEGORY_BACKUP
    if path_parts & ARCHIVE_DIRS:
        return FILE_CATEGORY_ARCHIVE
    if path_parts & LOG_DIRS:
        return FILE_CATEGORY_LOGS
    if path_parts & TEST_DIRS:
        return FILE_CATEGORY_TEST
    if path_parts & DOC_DIRS:
        return FILE_CATEGORY_DOCS
    if path_parts & ASSET_DIRS:
        return FILE_CATEGORY_ASSETS

    # Check extension-based categories
    if extension in LOG_EXTENSIONS or filename.endswith(".log"):
        return FILE_CATEGORY_LOGS
    if extension in DOC_EXTENSIONS:
        return FILE_CATEGORY_DOCS
    if extension in CONFIG_EXTENSIONS:
        return FILE_CATEGORY_CONFIG
    if extension in DATA_EXTENSIONS:
        return FILE_CATEGORY_DATA
    if extension in ASSET_EXTENSIONS:
        return FILE_CATEGORY_ASSETS
    if extension in ALL_CODE_EXTENSIONS:
        return FILE_CATEGORY_CODE

    # Default to code for unknown extensions in code directories
    return FILE_CATEGORY_CODE


def get_language(file_path: Path) -> str:
    """
    Detect the programming language of a file based on extension.

    Args:
        file_path: Path object for the file

    Returns:
        Language name string (e.g., "python", "javascript", "rust")
        Returns "unknown" if language cannot be determined.
    """
    extension = file_path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(extension, "unknown")


def should_skip_directory(dir_name: str) -> bool:
    """
    Check if a directory should be completely skipped during analysis.

    Args:
        dir_name: Name of the directory

    Returns:
        True if directory should be skipped, False otherwise.
    """
    return dir_name.lower() in SKIP_DIRS or dir_name in SKIP_DIRS


def should_count_for_metrics(file_path: Path) -> bool:
    """
    Check if a file should be counted toward code metrics.

    Only code and config files count toward line metrics.
    Docs, logs, backups, archives are tracked but don't inflate code metrics.

    Args:
        file_path: Path object for the file

    Returns:
        True if file should count toward code metrics.
    """
    category = get_file_category(file_path)
    return category in (FILE_CATEGORY_CODE, FILE_CATEGORY_CONFIG, FILE_CATEGORY_TEST)


def is_code_file(file_path: Path) -> bool:
    """
    Check if a file is a source code file.

    Args:
        file_path: Path object for the file

    Returns:
        True if file is source code.
    """
    extension = file_path.suffix.lower()
    return extension in ALL_CODE_EXTENSIONS


def is_web_file(file_path: Path) -> bool:
    """
    Check if a file is a web-related file (HTML, CSS, JS, Vue, etc.).

    Args:
        file_path: Path object for the file

    Returns:
        True if file is web-related.
    """
    extension = file_path.suffix.lower()
    web_extensions = (
        JS_EXTENSIONS
        | TS_EXTENSIONS
        | VUE_EXTENSIONS
        | CSS_EXTENSIONS
        | HTML_EXTENSIONS
        | SVELTE_EXTENSIONS
        | ASTRO_EXTENSIONS
    )
    return extension in web_extensions


def get_category_info(category: str) -> Dict[str, any]:
    """
    Get display information for a file category.

    Issue #665: Refactored to use module-level _CATEGORY_INFO constant.

    Args:
        category: Category string

    Returns:
        Dict with emoji, title, description, and priority flag.
    """
    return _CATEGORY_INFO.get(category, _DEFAULT_CATEGORY_INFO)
