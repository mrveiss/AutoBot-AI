# User Management System

A comprehensive user management system built with Node.js, Express, and MongoDB. This project demonstrates enterprise-level patterns for user authentication, authorization, and management.

## Features

### Core Functionality
- **User Registration & Authentication**: Secure user registration with JWT-based authentication
- **Role-Based Access Control (RBAC)**: Admin, User, and Guest roles with permission system
- **Password Security**: BCrypt hashing with configurable salt rounds
- **Account Management**: User activation, deactivation, suspension, and soft deletion
- **Profile Management**: User profile updates with validation
- **Permission System**: Granular permissions for fine-grained access control

### Security Features
- **Rate Limiting**: Configurable rate limits for different endpoints
- **Input Validation**: Comprehensive validation using express-validator
- **Security Headers**: Helmet.js for security headers
- **CORS Protection**: Configurable CORS policies
- **Account Lockout**: Automatic account lockout after failed login attempts
- **JWT Security**: Secure token generation and validation

### API Features
- **RESTful API**: Clean REST API design with proper HTTP methods
- **Pagination**: Efficient pagination for large datasets
- **Search Functionality**: Full-text search across user fields
- **Filtering**: Role-based and status-based filtering
- **Export Functionality**: User data export capabilities
- **Statistics**: User statistics and analytics

### Development Features
- **Error Handling**: Comprehensive error handling with custom error classes
- **Logging**: Structured logging with Winston
- **Documentation**: Detailed API documentation
- **Testing**: Unit and integration tests with Jest
- **Code Quality**: ESLint and Prettier configuration

## Technology Stack

- **Runtime**: Node.js 16+
- **Framework**: Express.js
- **Database**: MongoDB with Mongoose ODM
- **Authentication**: JSON Web Tokens (JWT)
- **Password hashing**: BCrypt
- **Validation**: Joi and express-validator
- **Logging**: Winston
- **Testing**: Jest and Supertest
- **Security**: Helmet, CORS, Rate limiting

## Installation

### Prerequisites
- Node.js (v16 or higher)
- MongoDB (v4.4 or higher)
- npm or yarn

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd user-management
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Environment configuration**
   ```bash
   cp .env.example .env
   ```
   Update the `.env` file with your configuration:
   ```env
   PORT=3000
   NODE_ENV=development
   MONGODB_URI=mongodb://localhost:27017/user-management
   JWT_SECRET=your-super-secret-jwt-key-here
   JWT_EXPIRES_IN=24h
   ```

4. **Start MongoDB**
   ```bash
   # Using MongoDB service
   sudo systemctl start mongod
   
   # Or using Docker
   docker run -d -p 27017:27017 --name mongodb mongo:latest
   ```

5. **Run the application**
   ```bash
   # Development mode
   npm run dev
   
   # Production mode
   npm start
   ```

## API Documentation

### Base URL
```
http://localhost:3000/api
```

### Authentication
Most endpoints require authentication. Include the JWT token in the Authorization header:
```
Authorization: Bearer <your-jwt-token>
```

### Endpoints

#### User Management
- `POST /users` - Create new user
- `GET /users` - Get all users (with pagination)
- `GET /users/:id` - Get user by ID
- `PUT /users/:id` - Update user
- `DELETE /users/:id` - Delete user (soft delete)
- `DELETE /users/:id/hard` - Permanently delete user

#### Authentication
- `POST /users/auth` - User login
- `PUT /users/:id/password` - Change password
- `PUT /users/:id/reset-password` - Reset password (admin only)

#### Search & Filtering
- `GET /users/search?q=query` - Search users
- `GET /users/active` - Get active users
- `GET /users/role/:role` - Get users by role

#### Permissions
- `PUT /users/:id/permissions` - Add permission
- `DELETE /users/:id/permissions` - Remove permission

#### Analytics
- `GET /users/stats` - Get user statistics
- `GET /users/export` - Export user data
- `GET /users/:id/activity` - Get user activity

### Example Requests

#### Create User
```bash
curl -X POST http://localhost:3000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "name": "John Doe",
    "email": "john@example.com",
    "password": "securepassword123",
    "age": 30,
    "role": "user"
  }'
```

#### Authenticate User
```bash
curl -X POST http://localhost:3000/api/users/auth \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "password": "securepassword123"
  }'
```

#### Get Users (with authentication)
```bash
curl -X GET http://localhost:3000/api/users \
  -H "Authorization: Bearer <your-jwt-token>"
```

## Testing

### Run Tests
```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### Test Structure
```
tests/
├── unit/
│   ├── models/
│   ├── services/
│   └── utils/
├── integration/
│   └── routes/
└── setup/
    └── testSetup.js
```

## Development

### Code Quality
```bash
# Linting
npm run lint

# Formatting
npm run format
```

### Project Structure
```
src/
├── config/
│   └── database.js
├── middleware/
│   ├── auth.js
│   ├── rateLimiter.js
│   └── validate.js
├── models/
│   └── User.js
├── routes/
│   └── userRoutes.js
├── services/
│   └── UserService.js
├── utils/
│   ├── errors.js
│   └── logger.js
└── server.js
```

### Database Schema

#### User Schema
```javascript
{
  id: String,           // UUID
  username: String,     // Unique, 3-20 chars
  email: String,        // Optional, unique
  name: String,         // Required, 1-100 chars
  age: Number,          // Optional, 0-150
  password: String,     // Hashed, min 8 chars
  role: String,         // admin, user, guest
  status: String,       // active, inactive, suspended, deleted
  lastLogin: Date,      // Last login timestamp
  loginAttempts: Number, // Failed login counter
  permissions: [String], // Array of permissions
  metadata: Object,     // Flexible metadata
  createdAt: Date,      // Auto-generated
  updatedAt: Date       // Auto-generated
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|-------|
| `PORT` | Server port | 3000 |
| `NODE_ENV` | Environment | development |
| `MONGODB_URI` | MongoDB connection string | mongodb://localhost:27017/user-management |
| `JWT_SECRET` | JWT secret key | Required |
| `JWT_EXPIRES_IN` | JWT expiration time | 24h |
| `ALLOWED_ORIGINS` | CORS allowed origins | http://localhost:3000 |
| `LOG_LEVEL` | Logging level | info |
| `BCRYPT_SALT_ROUNDS` | BCrypt salt rounds | 12 |

## Security Considerations

1. **Environment Variables**: Never commit sensitive data to version control
2. **JWT Secret**: Use a strong, random JWT secret in production
3. **Rate Limiting**: Adjust rate limits based on your requirements
4. **Input Validation**: All inputs are validated and sanitized
5. **Password Security**: Passwords are hashed using BCrypt with salt rounds
6. **Account Lockout**: Accounts are locked after 5 failed login attempts
7. **CORS**: Configure CORS origins for production
8. **Security Headers**: Helmet.js provides security headers

## Performance Optimizations

1. **Database Indexing**: Indexes on frequently queried fields
2. **Pagination**: Efficient pagination for large datasets
3. **Connection Pooling**: MongoDB connection pooling
4. **Compression**: Gzip compression for responses
5. **Caching**: Ready for Redis integration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please open an issue in the GitHub repository or contact the development team.

## Changelog

### v1.0.0
- Initial release
- User management functionality
- Authentication and authorization
- API endpoints
- Security features
- Testing suitet/models/
   ```

## Service Management

### SystemD Service Files

All services are managed via systemd with proper dependencies:

```bash
# Check service status
systemctl status autobot-backend
systemctl status autobot-frontend
systemctl status autobot-ai-stack
systemctl status autobot-npu-worker
systemctl status redis-stack-server

# Service logs
journalctl -u autobot-backend -f
journalctl -u autobot-frontend -f
```

### Service Dependencies

```
Redis (VM3) → Backend (VM2) → AI/ML (VM4) → Frontend (VM1) → Browser (VM5)
     ↑                                                               ↓
     └─────────────── Model Storage ← ─────────────────────────────────┘
```

## Monitoring & Health Checks

### Built-in Health Checks

```bash
# Run comprehensive health check
./utils/health-check.sh

# Individual service health
curl http://192.168.100.10/health  # Frontend
curl http://192.168.100.20:8001/api/health  # Backend
curl http://192.168.100.30:8080/health  # AI Stack
curl http://192.168.100.40:8081/health  # NPU Worker
redis-cli -h 192.168.100.50 ping  # Redis
```

### Log Aggregation

All logs are centralized on the Backend VM (VM2):
- **Location**: `/var/log/autobot/`
- **Retention**: 30 days, 100MB max per service
- **Format**: JSON structured logs

## Backup & Recovery

### Automated Backups

```bash
# Full system backup
./utils/backup.sh --full

# Service-specific backups
./utils/backup.sh --redis
./utils/backup.sh --models
./utils/backup.sh --configs
```

### Recovery Procedures

```bash
# Full system restore
./utils/restore.sh --full --from-backup=/path/to/backup

# Service-specific restore
./utils/restore.sh --redis --from-backup=/path/to/redis-backup
```

## Troubleshooting

### Common Issues

1. **VM Connectivity**:
   ```bash
   # Test network connectivity
   ansible all -m ping
   
   # Check firewall rules
   ansible all -m command -a "ufw status"
   ```

2. **Service Dependencies**:
   ```bash
   # Check service dependency tree
   systemctl list-dependencies autobot-backend
   ```

3. **Performance Issues**:
   ```bash
   # Monitor resource usage
   ansible all -m command -a "htop -n 1"
   ansible all -m command -a "free -h"
   ```

### Log Analysis

```bash
# Search logs across all VMs
./utils/search-logs.sh "error" --last-24h

# Performance monitoring
./utils/monitor-performance.sh --duration=1h
```

## Security

### Network Security
- Internal network isolation (192.168.100.0/24)
- Windows Firewall protection
- No direct internet exposure

### VM Security
- UFW firewall on each VM
- SSH key-based authentication
- Regular security updates via Ansible

### Application Security
- Service-specific user accounts
- File permission restrictions
- Encrypted inter-service communication

## Maintenance

### Regular Updates

```bash
# System package updates
ansible all -m apt -a "upgrade=yes update_cache=yes" --become

# AutoBot application updates
./deploy.sh --services --skip-data
```

### Performance Tuning

```bash
# Optimize database performance
ansible database -m command -a "redis-cli CONFIG SET save '60 1000'"

# Adjust service resource limits
# Edit files in templates/systemd/ and redeploy
```

## Migration Timeline

1. **Phase 1** (30 minutes): VM preparation and base system setup
2. **Phase 2** (45 minutes): Service installation and configuration
3. **Phase 3** (20 minutes): Data migration from Docker
4. **Phase 4** (15 minutes): Service startup and health checks
5. **Phase 5** (10 minutes): Validation and testing

**Total Deployment Time**: ~2 hours for complete migration

## Support & Documentation

- **Playbook Documentation**: See individual role README files
- **Configuration Reference**: Check `group_vars/` files for all options
- **Troubleshooting Guide**: See `docs/troubleshooting.md`
- **Performance Tuning**: See `docs/performance.md`

---

**Next Steps After Deployment:**

1. Verify all services are healthy
2. Update DNS entries if needed
3. Configure backup schedule
4. Set up monitoring dashboards
5. Run load testing to validate performance