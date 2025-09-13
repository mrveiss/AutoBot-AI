# User Management System (Python)

A comprehensive user management system built in Python for testing Code Index MCP's analysis capabilities.

## Features

- **User Management**: Create, update, delete, and search users
- **Authentication**: Password-based authentication with session management
- **Authorization**: Role-based access control (Admin, User, Guest)
- **Data Validation**: Comprehensive input validation and sanitization
- **Export/Import**: JSON and CSV export capabilities
- **CLI Interface**: Command-line interface for system management

## Project Structure

```
user_management/
├── models/
│   ├── __init__.py
│   ├── person.py          # Basic Person model
│   └── user.py            # User model with auth features
├── services/
│   ├── __init__.py
│   ├── user_manager.py    # User management service
│   └── auth_service.py    # Authentication service
├── utils/
│   ├── __init__.py
│   ├── validators.py      # Input validation utilities
│   ├── exceptions.py      # Custom exception classes
│   └── helpers.py         # Helper functions
├── tests/                 # Test directory (empty for now)
├── __init__.py
└── cli.py                 # Command-line interface
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install the package in development mode:
```bash
pip install -e .
```

## Usage

### Running the Demo

```bash
python main.py
```

### Using the CLI

```bash
# Create a new user
user-cli create-user --name "John Doe" --username "john" --age 30 --email "john@example.com"

# List all users
user-cli list-users

# Get user information
user-cli get-user john

# Update user
user-cli update-user john --age 31

# Delete user
user-cli delete-user john

# Search users
user-cli search "john"

# Show statistics
user-cli stats

# Export users
user-cli export --format json --output users.json
```

### Programmatic Usage

```python
from user_management import UserManager, UserRole
from user_management.services.auth_service import AuthService

# Create user manager
user_manager = UserManager()

# Create a user
user = user_manager.create_user(
    name="Jane Smith",
    username="jane",
    age=28,
    email="jane@example.com",
    role=UserRole.USER
)

# Set password
user.set_password("SecurePass123!")

# Authenticate
auth_service = AuthService(user_manager)
authenticated_user = auth_service.authenticate("jane", "SecurePass123!")

# Create session
session_id = auth_service.create_session(authenticated_user)
```

## Testing Features

This project tests the following Python language features:

- **Classes and Inheritance**: Person and User classes with inheritance
- **Dataclasses**: Modern Python data structures
- **Enums**: Role and status enumerations
- **Type Hints**: Comprehensive type annotations
- **Properties**: Getter/setter methods
- **Class Methods**: Factory methods and utilities
- **Static Methods**: Utility functions
- **Context Managers**: Resource management
- **Decorators**: Method decorators
- **Generators**: Iteration patterns
- **Exception Handling**: Custom exceptions
- **Package Structure**: Modules and imports
- **CLI Development**: Click framework integration
- **JSON/CSV Processing**: Data serialization
- **Regular Expressions**: Input validation
- **Datetime Handling**: Time-based operations
- **Cryptography**: Password hashing
- **File I/O**: Data persistence

## Dependencies

- **click**: Command-line interface framework
- **pytest**: Testing framework
- **pydantic**: Data validation (optional)

## License

MIT License - This is a sample project for testing purposes.ferences**: Stream operations
- **Optional**: Null-safe operations
- **Time API**: LocalDateTime usage

### Advanced Features
- **Concurrent Collections**: ConcurrentHashMap
- **Reflection**: Jackson serialization
- **File I/O**: NIO.2 Path and Files
- **Logging**: SLF4J with parameterized messages
- **Validation**: Input validation and sanitization

### Framework Integration
- **Maven**: Build lifecycle and dependency management
- **Jackson**: JSON serialization/deserialization
- **BCrypt**: Password hashing
- **Apache Commons**: Utility libraries
- **SLF4J**: Structured logging

### Design Patterns
- **Builder Pattern**: Object construction
- **Factory Pattern**: User creation
- **Repository Pattern**: Data access
- **Service Layer**: Business logic separation

## Dependencies

### Core Dependencies
- **Jackson Databind**: JSON processing
- **Jackson JSR310**: Java 8 time support
- **BCrypt**: Password hashing
- **Apache Commons Lang3**: Utilities
- **Apache Commons CSV**: CSV processing

### Logging
- **SLF4J API**: Logging facade
- **Logback Classic**: Logging implementation

### Testing
- **JUnit 5**: Testing framework
- **Mockito**: Mocking framework

## License

MIT License - This is a sample project for testing purposes.