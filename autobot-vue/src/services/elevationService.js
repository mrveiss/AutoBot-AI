/**
 * Elevation Service
 * Manages privilege escalation requests and dialog interactions
 */

import { ref, reactive } from 'vue';
import { apiService } from './api';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for elevationService
const logger = createLogger('elevationService');

class ElevationService {
  constructor() {
    this.pendingRequests = reactive(new Map());
    this.activeSession = ref(null);
    this.sessionExpiry = ref(null);
    this.elevationDialog = ref(null);
    
    // Start session monitoring
    this.startSessionMonitor();
  }

  /**
   * Register the elevation dialog component
   */
  registerDialog(dialogComponent) {
    this.elevationDialog.value = dialogComponent;
  }

  /**
   * Request elevation for a privileged operation
   */
  async requestElevation(operation, command, reason, riskLevel = 'MEDIUM') {
    try {
      // Issue #552: Fixed path to match backend /api/elevation/*
      const response = await apiService.post('/api/elevation/request', {
        operation,
        command,
        reason,
        risk_level: riskLevel
      });

      if (response.data.success) {
        const requestId = response.data.request_id;
        
        // Store pending request
        this.pendingRequests.set(requestId, {
          operation,
          command,
          reason,
          riskLevel,
          timestamp: new Date(),
          status: 'pending'
        });

        // Show elevation dialog
        return await this.showElevationDialog(requestId, operation, command, reason, riskLevel);
      }
      
      throw new Error(response.data.message || 'Failed to create elevation request');
    } catch (error) {
      logger.error('Elevation request failed:', error);
      throw error;
    }
  }

  /**
   * Show elevation dialog and wait for user response
   */
  async showElevationDialog(requestId, operation, command, reason, riskLevel) {
    return new Promise((resolve, reject) => {
      if (!this.elevationDialog.value) {
        reject(new Error('Elevation dialog not registered'));
        return;
      }

      // Set dialog props
      this.elevationDialog.value.show = true;
      this.elevationDialog.value.requestId = requestId;
      this.elevationDialog.value.operation = operation;
      this.elevationDialog.value.command = command;
      this.elevationDialog.value.reason = reason;
      this.elevationDialog.value.riskLevel = riskLevel;

      // Handle dialog events
      const handleApproved = (data) => {
        this.activeSession.value = data.sessionToken;
        this.updateSessionExpiry(15 * 60); // 15 minutes default
        resolve({
          approved: true,
          sessionToken: data.sessionToken
        });
        cleanup();
      };

      const handleCancelled = () => {
        resolve({
          approved: false,
          sessionToken: null
        });
        cleanup();
      };

      const cleanup = () => {
        this.elevationDialog.value.$off('approved', handleApproved);
        this.elevationDialog.value.$off('cancelled', handleCancelled);
      };

      this.elevationDialog.value.$on('approved', handleApproved);
      this.elevationDialog.value.$on('cancelled', handleCancelled);
    });
  }

  /**
   * Execute command with elevation
   */
  async executeElevatedCommand(command, sessionToken = null) {
    const token = sessionToken || this.activeSession.value;
    
    if (!token) {
      throw new Error('No active elevation session');
    }

    try {
      // Issue #552: Fixed path to match backend /api/elevation/*
      const response = await apiService.post(`/api/elevation/execute/${token}`, {
        command
      });

      if (response.data.success) {
        return {
          success: true,
          output: response.data.output,
          error: response.data.error,
          returnCode: response.data.return_code
        };
      }

      throw new Error(response.data.message || 'Command execution failed');
    } catch (error) {
      // If session expired, clear it and request new elevation
      if (error.response?.status === 401) {
        this.clearSession();
      }
      throw error;
    }
  }

  /**
   * Check if we have an active elevation session
   */
  hasActiveSession() {
    return !!this.activeSession.value && 
           this.sessionExpiry.value && 
           new Date() < this.sessionExpiry.value;
  }

  /**
   * Clear current elevation session
   */
  async clearSession() {
    if (this.activeSession.value) {
      try {
        // Issue #552: Fixed path to match backend /api/elevation/*
        await apiService.delete(`/api/elevation/session/${this.activeSession.value}`);
      } catch (error) {
        logger.error('Failed to revoke session:', error);
      }
    }
    
    this.activeSession.value = null;
    this.sessionExpiry.value = null;
  }

  /**
   * Update session expiry time
   */
  updateSessionExpiry(secondsFromNow) {
    this.sessionExpiry.value = new Date(Date.now() + secondsFromNow * 1000);
  }

  /**
   * Monitor session expiry
   */
  startSessionMonitor() {
    setInterval(() => {
      if (this.sessionExpiry.value && new Date() >= this.sessionExpiry.value) {
        this.clearSession();
      }
    }, 10000); // Check every 10 seconds
  }

  /**
   * Get all pending elevation requests
   */
  async getPendingRequests() {
    try {
      // Issue #552: Fixed path to match backend /api/elevation/*
      const response = await apiService.get('/api/elevation/pending');
      if (response.data.success) {
        return response.data.pending_requests;
      }
      return {};
    } catch (error) {
      logger.error('Failed to get pending requests:', error);
      return {};
    }
  }

  /**
   * Wrap a function to automatically request elevation if needed
   */
  withElevation(operation, reason, riskLevel = 'MEDIUM') {
    return async (originalFunction) => {
      return async (...args) => {
        try {
          // Try to execute normally first
          return await originalFunction(...args);
        } catch (error) {
          // If permission denied, request elevation
          if (error.message?.includes('permission denied') || 
              error.message?.includes('sudo') ||
              error.code === 'EACCES') {
            
            // Get command from error or function context
            const command = error.command || `${operation} operation`;
            
            // Request elevation
            const elevationResult = await this.requestElevation(
              operation,
              command,
              reason,
              riskLevel
            );

            if (elevationResult.approved) {
              // Retry with elevation
              return await originalFunction(...args, {
                elevationToken: elevationResult.sessionToken
              });
            } else {
              throw new Error('Elevation request cancelled by user');
            }
          }
          
          // Re-throw other errors
          throw error;
        }
      };
    };
  }
}

// Create singleton instance
const elevationService = new ElevationService();

export default elevationService;