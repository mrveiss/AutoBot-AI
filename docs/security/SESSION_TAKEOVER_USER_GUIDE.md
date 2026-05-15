# Session Takeover System - User Guide

## 🎯 **Quick Start Guide**

### **What is Session Takeover?**
Session Takeover allows you to **pause AI automation at any point**, perform **manual configurations**, and then **seamlessly resume** the automated workflow. You maintain full control while benefiting from AI assistance.

### **Key Benefits:**
- ✅ **Never lose control** - Pause automation instantly
- 🛡️ **Safety first** - Confirm dangerous commands before execution  
- 🔧 **Manual intervention** - Add custom steps between automated ones
- 📋 **Step-by-step approval** - See exactly what AI wants to execute
- 🚨 **Emergency controls** - Kill all processes immediately if needed

---

## 🖥️ **Terminal Interface Overview**

### **New Control Buttons (Terminal Header):**

1. **🛑 KILL** - Emergency stop all running processes
2. **⏸️ PAUSE / ▶️ RESUME** - Control automation flow
3. **⚡ INT** - Send Ctrl+C to current process
4. **🔄** - Reconnect terminal
5. **🗑️** - Clear terminal output

### **Visual Command Types:**
- **🤖 AUTOMATED** - Blue highlighting: Commands executed by AI
- **👤 MANUAL** - Green highlighting: Commands typed by you during manual control
- **📋 WORKFLOW INFO** - Purple highlighting: Workflow step information
- **⚠️ SYSTEM** - Standard highlighting: System messages and status updates

---

## 📋 **Step-by-Step Workflow Process**

### **1. AI Proposes Automated Workflow**
When you make requests like:
- *"Please install and configure a development environment"*
- *"Set up my server with nginx and SSL certificates"*
- *"Update my system and install security patches"*

**What happens:**
```
🚀 AUTOMATED WORKFLOW STARTED: Development Environment Setup
📋 4 steps planned. Use PAUSE button to take manual control at any time.
```

### **2. Step Confirmation Modal Appears**
Before each potentially risky command, you'll see a confirmation modal:

**Modal Contents:**
- **Step Counter**: "Step 2 of 4"
- **Command Preview**: `sudo apt install -y nodejs npm`
- **Description**: "Install Node.js and npm"
- **Explanation**: "This installs Node.js runtime and npm package manager for JavaScript development"
- **Risk Level**: Visual indicator (Low/Moderate/High/Critical)

**Your Options:**
- **✅ Execute & Continue** - Run the command and proceed to next step
- **⏭️ Skip This Step** - Skip this command and continue with the workflow
- **👤 Take Manual Control** - Pause automation and switch to manual mode

### **3. Manual Control Mode**
When you click "👤 Take Manual Control":

```
👤 MANUAL CONTROL TAKEN - Complete your manual steps, then click RESUME to continue workflow.
```

**In Manual Mode:**
- Type any commands you want
- Perform custom configurations
- Install additional software
- Modify config files
- All your commands show with 👤 MANUAL prefix

**When Ready:**
- Click **▶️ RESUME** button
- Automation continues from the next planned step
- Your manual work is preserved

---

## 🚨 **Emergency Controls**

### **Emergency Kill (🛑 KILL)**
**When to use:** Runaway processes, infinite loops, dangerous commands

**What it does:**
1. Shows confirmation modal with all running processes
2. Lists each process with PID and command
3. On confirmation, sends SIGKILL to all processes
4. Clears all process tracking
5. Shows emergency kill notification

**Process:**
```
🛑 EMERGENCY KILL: All processes terminated by user
```

### **Process Interrupt (⚡ INT)**
**When to use:** Stop current running command

**What it does:**
- Sends Ctrl+C (SIGINT) to the current process
- Shows interrupt notification: `^C (Process interrupted by user)`
- Safer than emergency kill for single process termination

### **Automation Pause (⏸️ PAUSE)**
**When to use:** Need to perform manual steps mid-workflow

**What it does:**
- Pauses automation at current step
- Enables manual command input
- Preserves workflow state for later resumption
- Button changes to **▶️ RESUME** with green pulsing animation

---

## 🎮 **Usage Scenarios**

### **Scenario 1: Standard Automation with Approval**

**User Request:** *"Please set up a web server with SSL"*

**Workflow Flow:**
1. **AI Creates Workflow:** 6 steps planned
2. **Step 1 Modal:** "Install nginx" → User clicks **✅ Execute & Continue**
3. **Step 2 Modal:** "Configure firewall" → User clicks **✅ Execute & Continue**  
4. **Step 3 Modal:** "Generate SSL certificates" → User clicks **✅ Execute & Continue**
5. **Step 4 Modal:** "Configure SSL in nginx" → User clicks **✅ Execute & Continue**
6. **Steps 5-6:** Auto-execute (verification steps, no confirmation needed)
7. **Completion:** `✅ Workflow completed successfully`

### **Scenario 2: Manual Intervention Required**

**User Request:** *"Install Docker and set up my custom application"*

**Workflow Flow:**
1. **Steps 1-3:** Install Docker, start service, verify installation
2. **Step 4 Modal:** "Clone application repository" → User clicks **👤 Take Manual Control**
3. **Manual Mode Activated:**
   ```
   👤 MANUAL CONTROL TAKEN - Complete your manual steps, then click RESUME.
   ```
4. **User Manual Commands:**
   ```
   👤 MANUAL: cd /opt
   👤 MANUAL: git clone https://github.com/myuser/myapp.git
   👤 MANUAL: cd myapp
   👤 MANUAL: nano docker-compose.yml  # Custom configuration
   👤 MANUAL: docker-compose up -d --build
   ```
5. **User Clicks ▶️ RESUME**
6. **Automation Continues:** Remaining verification and cleanup steps

### **Scenario 3: Emergency Intervention**

**Situation:** AI starts a command that's taking too long or seems problematic

**User Actions:**
1. **Notices Problem:** Command running for 10+ minutes unexpectedly
2. **Clicks 🛑 KILL:** Emergency kill modal appears
3. **Sees Process List:**
   ```
   PID 1234: find / -name "*.log" -exec rm {} \;
   PID 1235: backup_script.sh
   ```
4. **Clicks "🛑 KILL ALL PROCESSES"**
5. **System Response:**
   ```
   🛑 EMERGENCY KILL: All processes terminated by user
   ```
6. **User Can:** Investigate what went wrong, then manually restart with corrections

### **Scenario 4: High-Risk Command Confirmation**

**AI Proposes:** `sudo rm -rf /var/log/old_logs/`

**System Response:** High-risk command modal appears with:
- **Risk Level:** HIGH (red highlighting with warning animation)
- **Risk Reasons:**
  - Command uses sudo (elevated privileges)
  - Command performs recursive deletion
  - Could delete important system files
- **Warning Message:** "This command may delete files permanently"

**User Options:**
- Most users click **❌ Cancel** and suggest a safer alternative
- Experienced users might click **⚡ Execute Command** after reviewing

---

## ⚙️ **Configuration and Customization**

### **Risk Assessment Levels**

**🟢 LOW RISK** (Auto-execute or minimal confirmation)
- `ls`, `cd`, `cat`, `echo`, `grep`
- Read-only operations
- Simple navigation commands

**🟡 MODERATE RISK** (Confirmation recommended)
- `sudo apt install`, `systemctl restart`
- Package management with sudo
- Service management operations

**🟠 HIGH RISK** (Confirmation required)
- `rm -rf`, `chmod 777 /`, `killall -9`
- Bulk deletion operations
- Permission changes on system directories

**🔴 CRITICAL RISK** (Strong confirmation required)
- `rm -rf /`, `dd of=/dev/sda`, `mkfs.*`
- System-destroying operations
- Disk formatting and partitioning

### **Automation Modes**

**SEMI_AUTOMATIC** (Default)
- Requires user confirmation for moderate+ risk commands
- Shows step confirmation modals
- Allows manual intervention at any point

**AUTOMATIC**
- Auto-executes low and moderate risk commands
- Still requires confirmation for high/critical risk
- Faster execution for routine operations

**MANUAL**
- All commands require explicit user approval
- Maximum control and safety
- Best for learning or high-security environments

---

## 🔧 **Troubleshooting**

### **Common Issues and Solutions**

**Issue:** "Workflow automation not available"
**Solution:** Backend components not loaded. Check server logs and restart AutoBot.

**Issue:** Terminal not responding to commands
**Solution:** 
1. Try clicking **🔄 Reconnect** button
2. Check WebSocket connection in browser console
3. Restart terminal session

**Issue:** Emergency kill not working
**Solution:**
1. Try **⚡ INT** button first for single process
2. Check if processes are running with different user permissions
3. Contact system administrator for manual process cleanup

**Issue:** Workflows not starting from chat
**Solution:**
1. Use more specific language: "install", "setup", "configure"
2. Check that workflow automation is enabled
3. Verify chat session has associated terminal

**Issue:** Step confirmation modal not appearing
**Solution:**
1. Check browser popup blockers
2. Verify JavaScript is enabled
3. Try refreshing the page and starting a new workflow

### **Best Practices**

1. **Always Review Commands:** Read the command and explanation before clicking Execute
2. **Use Manual Control for Complex Tasks:** Take control when you need to perform specific configurations
3. **Test in Safe Environment First:** Try workflows in development/test environments before production
4. **Keep Emergency Controls Ready:** Know where the KILL button is before starting complex workflows
5. **Monitor Process Lists:** Keep an eye on running processes during automation
6. **Save Important Work:** Backup important files before running system-modifying workflows

### **Getting Help**

**In-Application Help:**
- Hover over any button for tooltip explanations
- Right-click terminal for context menu options
- Check system logs for detailed error information

**Documentation:**
- Full API documentation available at `/api/docs`
- Workflow examples in `/docs/workflow-examples/`
- Video tutorials at `/help/tutorials/`

**Support Channels:**
- GitHub Issues for bug reports
- Community Discord for questions
- Documentation updates at `/help/session-takeover/`

---

## 🎉 **Advanced Features**

### **Workflow Templates**
Pre-built workflows for common tasks:
- **System Update**: Safe system updating with confirmations
- **Dev Environment**: Complete development setup
- **Security Scan**: Security audit and hardening
- **Backup Creation**: Automated backup procedures

### **Custom Workflow Creation**
Create your own workflows via API:
```python
# Example: Custom workflow creation
workflow_data = {
    "name": "My Custom Setup",
    "steps": [
        {
            "command": "echo 'Starting custom setup'",
            "description": "Initialize process",
            "requires_confirmation": False
        },
        {
            "command": "sudo apt install custom-package",
            "description": "Install custom software",
            "requires_confirmation": True
        }
    ]
}
```

### **Integration with External Tools**
- **CI/CD Pipelines**: Trigger workflows from deployment pipelines
- **Monitoring Systems**: Automatically run maintenance workflows
- **Configuration Management**: Integrate with Ansible, Chef, Puppet

### **Workflow Sharing and Export**
- Export successful workflows for reuse
- Share workflows with team members
- Import community-contributed workflows

---

**🚀 The Session Takeover System transforms AutoBot from a simple assistant into a collaborative automation partner where you maintain full control while benefiting from AI efficiency!**

*Need help? Click the 🤖 Test Workflow button in the terminal footer to try a safe example workflow.*