# User Management System (Go)

A comprehensive user management system built in Go for testing Code Index MCP's analysis capabilities.

## Features

- **User Management**: Create, update, delete, and search users
- **REST API**: Full HTTP API with JSON responses
- **Authentication**: BCrypt password hashing and JWT tokens
- **Authorization**: Role-based access control (Admin, User, Guest)
- **Database**: SQLite with GORM ORM
- **Pagination**: Efficient pagination for large datasets
- **Search**: Full-text search across users
- **Export**: JSON export functionality
- **Logging**: Structured logging with middleware
- **CORS**: Cross-origin resource sharing support

## Project Structure

```
user-management/
├── cmd/
│   ├── server/
│   │   └── main.go           # HTTP server entry point
│   └── cli/
│       └── main.go           # CLI application
├── internal/
│   ├── models/
│   │   └── user.go           # User model and types
│   ├── services/
│   │   └── user_service.go   # Business logic
│   └── utils/
│       └── types.go          # Utility types and helpers
├── pkg/
│   └── api/
│       └── user_handler.go   # HTTP handlers
├── go.mod                    # Go module file
├── go.sum                    # Go dependencies
└── README.md                 # This file
```

## Technologies Used

- **Go 1.21**: Modern Go with generics and latest features
- **Gin**: HTTP web framework
- **GORM**: ORM for database operations
- **SQLite**: Embedded database
- **UUID**: Unique identifiers
- **BCrypt**: Password hashing
- **JWT**: JSON Web Tokens (planned)
- **Viper**: Configuration management
- **Cobra**: CLI framework

## Build and Run

### Prerequisites

- Go 1.21 or higher

### Install Dependencies

```bash
go mod tidy
```

### Run HTTP Server

```bash
go run cmd/server/main.go
```

The server will start on `http://localhost:8080`

### Run CLI

```bash
go run cmd/cli/main.go
```

### Build

```bash
# Build server
go build -o bin/server cmd/server/main.go

# Build CLI
go build -o bin/cli cmd/cli/main.go
```

## API Endpoints

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/users` | Create a new user |
| `GET` | `/api/v1/users` | Get all users (paginated) |
| `GET` | `/api/v1/users/:id` | Get user by ID |
| `PUT` | `/api/v1/users/:id` | Update user |
| `DELETE` | `/api/v1/users/:id` | Delete user |
| `GET` | `/api/v1/users/search` | Search users |
| `GET` | `/api/v1/users/stats` | Get user statistics |
| `GET` | `/api/v1/users/export` | Export users |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | User login |
| `POST` | `/api/v1/auth/logout` | User logout |
| `POST` | `/api/v1/auth/change-password` | Change password |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/admin/users/:id/reset-password` | Reset user password |
| `POST` | `/api/v1/admin/users/:id/permissions` | Add permission |
| `DELETE` | `/api/v1/admin/users/:id/permissions` | Remove permission |

## Usage Examples

### Create User

```bash
curl -X POST http://localhost:8080/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "name": "John Doe",
    "age": 30,
    "password": "password123"
  }'
```

### Get Users

```bash
curl http://localhost:8080/api/v1/users?page=1&page_size=10
```

### Search Users

```bash
curl http://localhost:8080/api/v1/users/search?q=john&page=1&page_size=10
```

### Login

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

### Get Statistics

```bash
curl http://localhost:8080/api/v1/users/stats
```

## Programmatic Usage

```go
package main

import (
    "github.com/example/user-management/internal/models"
    "github.com/example/user-management/internal/services"
    "gorm.io/driver/sqlite"
    "gorm.io/gorm"
)

func main() {
    // Initialize database
    db, err := gorm.Open(sqlite.Open("users.db"), &gorm.Config{})
    if err != nil {
        panic(err)
    }
    
    // Auto migrate
    db.AutoMigrate(&models.User{})
    
    // Initialize service
    userService := services.NewUserService(db)
    
    // Create user
    req := &models.UserRequest{
        Username: "alice",
        Email:    "alice@example.com",
        Name:     "Alice Smith",
        Age:      25,
        Password: "password123",
        Role:     models.RoleUser,
    }
    
    user, err := userService.CreateUser(req)
    if err != nil {
        panic(err)
    }
    
    // Authenticate user
    authUser, err := userService.AuthenticateUser("alice", "password123")
    if err != nil {
        panic(err)
    }
    
    // Get statistics
    stats, err := userService.GetUserStats()
    if err != nil {
        panic(err)
    }
}
```

## Testing Features

This project tests the following Go language features:

### Core Language Features
- **Structs and Methods**: User model with associated methods
- **Interfaces**: Service and handler interfaces
- **Pointers**: Efficient memory management
- **Error Handling**: Comprehensive error handling patterns
- **Packages**: Modular code organization
- **Imports**: Internal and external package imports

### Modern Go Features
- **Generics**: Type-safe collections (Go 1.18+)
- **Modules**: Dependency management with go.mod
- **Context**: Request context handling
- **Channels**: Concurrent programming (in background tasks)
- **Goroutines**: Concurrent execution
- **JSON Tags**: Struct field mapping

### Advanced Features
- **Reflection**: GORM model reflection
- **Build Tags**: Conditional compilation
- **Embedding**: Struct embedding for composition
- **Type Assertions**: Interface type checking
- **Panic/Recover**: Error recovery mechanisms

### Framework Integration
- **Gin**: HTTP router and middleware
- **GORM**: ORM with hooks and associations
- **UUID**: Unique identifier generation
- **BCrypt**: Cryptographic hashing
- **SQLite**: Embedded database

### Design Patterns
- **Repository Pattern**: Data access layer
- **Service Layer**: Business logic separation
- **Dependency Injection**: Service composition
- **Middleware Pattern**: HTTP request processing
- **Factory Pattern**: Service creation

## Dependencies

### Core Dependencies
- **gin-gonic/gin**: Web framework
- **gorm.io/gorm**: ORM
- **gorm.io/driver/sqlite**: SQLite driver
- **google/uuid**: UUID generation
- **golang.org/x/crypto**: Cryptographic functions

### CLI Dependencies
- **spf13/cobra**: CLI framework
- **spf13/viper**: Configuration management

### Development Dependencies
- **testify**: Testing framework
- **mockery**: Mock generation

## Configuration

The application can be configured using environment variables or a configuration file:

```yaml
database:
  driver: sqlite
  database: users.db
  
server:
  port: 8080
  host: localhost
  
jwt:
  secret_key: your-secret-key
  expiration_hours: 24
```

## Development

### Run Tests

```bash
go test ./...
```

### Generate Mocks

```bash
mockery --all
```

### Format Code

```bash
gofmt -w .
```

### Lint Code

```bash
golangci-lint run
```

## License

MIT License - This is a sample project for testing purposes.