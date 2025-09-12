# AutoBot VM Security Utilities

## Security-First Approach for Single-User VMs

**Environment**: All remote VMs (172.16.168.21-25) have only the `autobot` user - simplified single-user environment.

### Password Handling
- **Interactive Prompts**: All password requests prompt the user interactively
- **No Hardcoded Credentials**: Scripts never contain hardcoded passwords
- **Secure Input**: Passwords are read with `-s` flag to prevent terminal display
- **Optional Authentication**: Users can skip password-required operations

### Available Utilities

#### 1. `setup-passwordless-sudo.sh`
- Configures passwordless sudo for autobot user across all VMs
- Prompts for password interactively for each VM
- Checks if passwordless sudo is already configured before prompting

#### 2. `secure-vm-exec.sh`
- Provides secure command execution functions for VM scripts
- Handles both passwordless and password-required scenarios
- Functions available:
  - `secure_vm_exec()` - Execute any command with password handling
  - `check_passwordless_sudo()` - Check if passwordless sudo is configured
  - `secure_package_install()` - Install packages with secure authentication

### Usage Examples

```bash
# Source the utility functions
source scripts/utilities/secure-vm-exec.sh

# Check passwordless sudo status
check_passwordless_sudo "172.16.168.21" "frontend"

# Install packages securely
secure_package_install "172.16.168.25" "browser" "xvfb" "netcat-openbsd"

# Execute command with password handling
secure_vm_exec "172.16.168.23" "redis" "sudo systemctl restart redis-stack-server"
```

### Security Benefits
1. **User Control**: Users decide when to provide passwords
2. **No Credential Exposure**: Passwords never stored in scripts or logs  
3. **Flexible Authentication**: Works with both passwordless and password-based sudo
4. **Graceful Degradation**: Operations continue even if some auth operations are skipped
5. **Audit Trail**: Clear logging of authentication attempts and results

### Single-User Environment Advantages
Since all VMs have only the `autobot` user:
- **Simplified Permission Model**: No multi-user conflicts or permission complexity
- **Consistent Environment**: Same user context across all VMs
- **Reduced Attack Surface**: No other user accounts to secure
- **Streamlined Administration**: Single identity to manage across infrastructure

**Security Note**: While single-user VMs simplify administration, ensure the `autobot` user password is strong and regularly rotated across all VMs.

### Best Practices
- Always use interactive password prompts
- Check for passwordless sudo before requesting passwords
- Provide clear context about why passwords are needed
- Allow users to skip operations requiring elevated privileges
- Use secure SSH key authentication as the primary method