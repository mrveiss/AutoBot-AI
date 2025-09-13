# Test Projects for Code Index MCP

This directory contains comprehensive test projects designed to validate and demonstrate the capabilities of the Code Index MCP server. Each project represents a realistic, enterprise-level codebase that showcases different programming languages, frameworks, and architectural patterns.

## Project Structure

```
test/
├── sample-projects/
│   ├── python/
│   │   └── user_management/          # Python user management system
│   ├── java/
│   │   └── user-management/          # Java Spring Boot user management
│   ├── go/
│   │   └── user-management/          # Go Gin user management API
│   ├── javascript/
│   │   └── user-management/          # Node.js Express user management
│   ├── typescript/
│   │   └── user-management/          # TypeScript Express user management
│   └── objective-c/                  # Objective-C test files
└── README.md                         # This file
```

## Sample Projects Overview

Each sample project implements a comprehensive user management system with the following core features:

### Common Features Across All Projects
- **User Registration & Authentication**: Secure user registration with password hashing
- **Role-Based Access Control (RBAC)**: Admin, User, and Guest roles with permissions
- **CRUD Operations**: Complete Create, Read, Update, Delete functionality
- **Search & Filtering**: Full-text search and role/status-based filtering
- **Pagination**: Efficient pagination for large datasets
- **Input Validation**: Comprehensive validation and sanitization
- **Error Handling**: Structured error handling with custom error classes
- **Logging**: Structured logging for debugging and monitoring
- **Security**: Password hashing, rate limiting, and security headers
- **Data Export**: User data export functionality
- **Statistics**: User analytics and statistics

### Language-Specific Implementation Details

#### Python Project (`python/user_management/`)
- **Framework**: Flask-based web application
- **Database**: SQLAlchemy ORM with SQLite
- **Authentication**: JWT tokens with BCrypt password hashing
- **Structure**: Clean package structure with models, services, and utilities
- **Features**: CLI interface, comprehensive validation, and export functionality

**Key Files:**
- `models/person.py` - Base Person model
- `models/user.py` - User model with authentication
- `services/user_manager.py` - Business logic layer
- `services/auth_service.py` - Authentication service
- `utils/` - Validation, exceptions, and helper utilities
- `cli.py` - Command-line interface

#### Java Project (`java/user-management/`)
- **Framework**: Spring Boot with Spring Data JPA
- **Database**: H2 in-memory database with JPA
- **Authentication**: JWT tokens with BCrypt
- **Structure**: Maven project with standard Java package structure
- **Features**: REST API, validation annotations, and comprehensive testing

**Key Files:**
- `model/User.java` - JPA entity with validation
- `service/UserService.java` - Business logic service
- `controller/UserController.java` - REST API endpoints
- `util/` - Validation, exceptions, and utilities
- `Application.java` - Spring Boot application entry point

#### Go Project (`go/user-management/`)
- **Framework**: Gin web framework with GORM
- **Database**: SQLite with GORM ORM
- **Authentication**: JWT tokens with BCrypt
- **Structure**: Clean Go module structure with internal packages
- **Features**: High-performance API, middleware, and concurrent processing

**Key Files:**
- `internal/models/user.go` - User model with GORM
- `internal/services/user_service.go` - Business logic
- `pkg/api/handlers/user_handler.go` - HTTP handlers
- `pkg/middleware/` - Authentication and validation middleware
- `cmd/server/main.go` - Application entry point

#### JavaScript Project (`javascript/user-management/`)
- **Framework**: Express.js with Mongoose
- **Database**: MongoDB with Mongoose ODM
- **Authentication**: JWT tokens with BCrypt
- **Structure**: Modern Node.js project with ES6+ features
- **Features**: Async/await, middleware, and comprehensive error handling

**Key Files:**
- `src/models/User.js` - Mongoose model with validation
- `src/services/UserService.js` - Business logic service
- `src/routes/userRoutes.js` - Express routes
- `src/middleware/` - Authentication and validation middleware
- `src/server.js` - Express application setup

#### TypeScript Project (`typescript/user-management/`)
- **Framework**: Express.js with Mongoose (TypeScript)
- **Database**: MongoDB with Mongoose ODM
- **Authentication**: JWT tokens with BCrypt
- **Structure**: Type-safe Node.js project with comprehensive interfaces
- **Features**: Full type safety, interfaces, and advanced TypeScript features

**Key Files:**
- `src/types/User.ts` - TypeScript interfaces and types
- `src/models/User.ts` - Mongoose model with TypeScript
- `src/services/UserService.ts` - Typed business logic service
- `src/routes/userRoutes.ts` - Typed Express routes
- `src/server.ts` - TypeScript Express application

#### Objective-C Project (`objective-c/`)
- **Framework**: Foundation classes
- **Features**: Classes, properties, methods, protocols
- **Structure**: Traditional .h/.m file structure

**Key Files:**
- `Person.h/.m` - Person class with properties
- `UserManager.h/.m` - User management functionality
- `main.m` - Application entry point

## Testing the Code Index MCP

These projects are designed to test various aspects of the Code Index MCP:

### File Analysis Capabilities
- **Language Detection**: Automatic detection of programming languages
- **Syntax Parsing**: Parsing of different syntax structures
- **Import/Dependency Analysis**: Understanding of module dependencies
- **Code Structure**: Recognition of classes, functions, and interfaces

### Search and Navigation
- **Symbol Search**: Finding functions, classes, and variables
- **Cross-Reference**: Finding usage of symbols across files
- **Fuzzy Search**: Approximate matching for typos and partial queries
- **Pattern Matching**: Regular expression and pattern-based searches

### Code Intelligence
- **Function Signatures**: Understanding of function parameters and return types
- **Variable Types**: Type inference and tracking
- **Scope Analysis**: Understanding of variable and function scope
- **Documentation**: Parsing of comments and documentation

### Performance Testing
- **Large Codebases**: Testing with realistic project sizes
- **Complex Structures**: Nested packages and deep directory structures
- **Multiple File Types**: Mixed file types within projects
- **Concurrent Access**: Multiple simultaneous search operations

## Running the Projects

Each project includes comprehensive setup instructions in its respective README.md file. General steps:

1. Navigate to the project directory
2. Install dependencies using the appropriate package manager
3. Set up environment variables (see .env.example files)
4. Run the application using the provided scripts
5. Test the API endpoints using the provided examples

### Quick Start Examples

```bash
# Python project
cd test/sample-projects/python/user_management
pip install -r requirements.txt
python cli.py

# Java project
cd test/sample-projects/java/user-management
mvn spring-boot:run

# Go project
cd test/sample-projects/go/user-management
go run cmd/server/main.go

# JavaScript project
cd test/sample-projects/javascript/user-management
npm install
npm run dev

# TypeScript project
cd test/sample-projects/typescript/user-management
npm install
npm run dev
```

## MCP Server Testing

To test the Code Index MCP server with these projects:

1. **Set Project Path**: Use the `set_project_path` tool to point to a project directory
2. **Index Files**: The server will automatically index all files in the project
3. **Search Testing**: Test various search queries and patterns
4. **Analysis Testing**: Use the analysis tools to examine code structure
5. **Performance Testing**: Measure response times and resource usage

### Example MCP Commands

```bash
# Set project path
set_project_path /path/to/test/sample-projects/python/user_management

# Search for user-related functions
search_code_advanced "def create_user" --file-pattern "*.py"

# Find all authentication-related code
search_code_advanced "auth" --fuzzy true

# Get file summary
get_file_summary models/user.py

# Find TypeScript interfaces
search_code_advanced "interface.*User" --regex true --file-pattern "*.ts"
```

## Contributing

When adding new test projects:

1. Follow the established patterns and structure
2. Implement all core features consistently
3. Include comprehensive documentation
4. Add appropriate test cases
5. Update this README with project details

## Security Considerations

All test projects include:
- Secure password hashing (BCrypt)
- Input validation and sanitization
- Rate limiting and security headers
- JWT token-based authentication
- Environment variable configuration
- Proper error handling without information disclosure

## Future Enhancements

Potential additions to the test suite:
- **Rust Project**: Systems programming language example
- **C++ Project**: Complex C++ codebase with templates
- **C# Project**: .NET Core application
- **PHP Project**: Laravel-based web application
- **Ruby Project**: Rails application
- **Swift Project**: iOS application structure
- **Kotlin Project**: Android/JVM application