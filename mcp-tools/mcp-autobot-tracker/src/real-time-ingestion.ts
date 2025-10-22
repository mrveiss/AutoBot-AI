import { createClient } from 'redis';
import { v4 as uuidv4 } from 'uuid';
import * as fs from 'fs/promises';
import * as path from 'path';
import { Tail } from 'tail';
import { NetworkConstants } from './constants/network.js';
import { PathConstants } from './constants/paths.js';

interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  tool_calls?: any[];
}

export class RealTimeIngestion {
  private redis: ReturnType<typeof createClient> | null = null;
  private conversationBuffer: Map<string, ConversationMessage[]> = new Map();
  private watchedFiles: Map<string, any> = new Map();
  private isRunning = false;

  async initialize() {
    this.redis = createClient({
      socket: { host: NetworkConstants.REDIS_VM_IP, port: NetworkConstants.REDIS_PORT },
      database: 10
    });

    await this.redis.connect();
    console.log('[RealTimeIngestion] Connected to Redis DB 10');

    this.isRunning = true;
    this.startConversationWatching();
  }

  private async startConversationWatching() {
    console.log('[RealTimeIngestion] Starting real-time conversation monitoring...');

    // Watch for new conversation files in AutoBot's chat history
    const chatHistoryPaths = [
      PathConstants.CONVERSATIONS_DIR,
      PathConstants.CHAT_HISTORY_DIR,
      PathConstants.CHAT_LOG
    ];

    for (const chatPath of chatHistoryPaths) {
      try {
        // Check if path exists
        const stats = await fs.stat(chatPath).catch(() => null);
        if (stats) {
          if (stats.isDirectory()) {
            await this.watchDirectory(chatPath);
          } else if (stats.isFile()) {
            await this.watchFile(chatPath);
          }
        }
      } catch (error) {
        console.log(`[RealTimeIngestion] Cannot watch ${chatPath}:`, (error as Error).message);
      }
    }

    // Also watch for conversation exports from AutoBot frontend
    this.startConversationBufferProcessing();
  }

  private async watchDirectory(dirPath: string) {
    console.log(`[RealTimeIngestion] Watching directory: ${dirPath}`);

    // Initial scan for existing files
    try {
      const files = await fs.readdir(dirPath);
      for (const file of files) {
        if (file.endsWith('.json') || file.endsWith('.log')) {
          await this.watchFile(path.join(dirPath, file));
        }
      }
    } catch (error) {
      console.log(`[RealTimeIngestion] Error scanning directory ${dirPath}:`, (error as Error).message);
    }
  }

  private async watchFile(filePath: string) {
    if (this.watchedFiles.has(filePath)) {
      return; // Already watching
    }

    console.log(`[RealTimeIngestion] Watching file: ${filePath}`);

    try {
      const tail = new Tail(filePath, {
        fromBeginning: false,
        follow: true,
        logger: console
      });

      tail.on('line', async (line: string) => {
        await this.processConversationLine(line, filePath);
      });

      tail.on('error', (error: any) => {
        console.error(`[RealTimeIngestion] Error watching ${filePath}:`, error);
      });

      this.watchedFiles.set(filePath, tail);
    } catch (error) {
      console.log(`[RealTimeIngestion] Cannot watch file ${filePath}:`, (error as Error).message);
    }
  }

  private async processConversationLine(line: string, filePath: string) {
    if (!line.trim()) return;

    try {
      // Try to parse as JSON conversation message
      const data = JSON.parse(line);

      if (this.isConversationMessage(data)) {
        await this.bufferMessage(data, filePath);
      }
    } catch (error) {
      // Not JSON - check if it's a structured log line with conversation data
      await this.parseLogLine(line, filePath);
    }
  }

  private isConversationMessage(data: any): data is ConversationMessage {
    return data &&
           typeof data === 'object' &&
           ['user', 'assistant', 'system'].includes(data.role) &&
           typeof data.content === 'string';
  }

  private async parseLogLine(line: string, filePath: string) {
    // Parse various log formats that might contain conversation data
    const patterns = [
      // AutoBot chat log format
      /\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\] (user|assistant|system): (.+)/,
      // Standard chat format
      /(user|assistant|system) \(([^)]+)\): (.+)/,
      // Claude API format
      /{"role":"(user|assistant|system)","content":"([^"]+)"}/
    ];

    for (const pattern of patterns) {
      const match = line.match(pattern);
      if (match) {
        const message: ConversationMessage = {
          role: match[2] as 'user' | 'assistant' | 'system',
          content: match[3] || match[2],
          timestamp: match[1] || new Date().toISOString()
        };

        await this.bufferMessage(message, filePath);
        break;
      }
    }
  }

  private async bufferMessage(message: ConversationMessage, source: string) {
    const sessionKey = `${source}-${new Date(message.timestamp).toDateString()}`;

    if (!this.conversationBuffer.has(sessionKey)) {
      this.conversationBuffer.set(sessionKey, []);
    }

    this.conversationBuffer.get(sessionKey)!.push(message);
    console.log(`[RealTimeIngestion] Buffered message from ${source}: ${message.content.substring(0, 50)}...`);
  }

  private startConversationBufferProcessing() {
    // Process buffered conversations every 30 seconds
    setInterval(async () => {
      if (!this.isRunning) return;

      for (const [sessionKey, messages] of this.conversationBuffer) {
        if (messages.length >= 2) { // At least user + assistant exchange
          await this.processBufferedConversation(sessionKey, messages);
          this.conversationBuffer.delete(sessionKey);
        }
      }
    }, 30000); // 30 seconds
  }

  private async processBufferedConversation(sessionKey: string, messages: ConversationMessage[]) {
    if (!this.redis) return;

    console.log(`[RealTimeIngestion] Processing buffered conversation: ${sessionKey} (${messages.length} messages)`);

    const sessionId = `realtime-${uuidv4()}`;
    const timestamp = new Date().toISOString();

    // Extract tasks from the conversation
    const tasks = this.extractTasks(messages, sessionId);
    const errors = this.extractErrors(messages, sessionId);

    // Store conversation session
    const sessionData = {
      session_id: sessionId,
      source: sessionKey,
      created_at: timestamp,
      updated_at: timestamp,
      message_count: messages.length,
      tasks_extracted: tasks.length,
      errors_extracted: errors.length,
      topic: this.extractTopic(messages),
      status: 'active',
      participants: this.extractParticipants(messages),
      conversation_type: 'real_time_ingestion',
      ingestion_method: 'file_watching'
    };

    await this.redis.hSet('chat:sessions', sessionId, JSON.stringify(sessionData));

    // Store tasks
    for (const task of tasks) {
      await this.redis.hSet('tasks:all', task.id, JSON.stringify(task));
      await this.redis.sAdd(`chat:${sessionId}:tasks`, task.id);
    }

    // Store errors
    for (const error of errors) {
      await this.redis.hSet('errors:all', error.id, JSON.stringify(error));
      await this.redis.lPush('errors:recent', error.id);
    }

    await this.redis.lTrim('errors:recent', 0, 999);

    console.log(`[RealTimeIngestion] Stored conversation: ${tasks.length} tasks, ${errors.length} errors`);
  }

  private extractTasks(messages: ConversationMessage[], sessionId: string): any[] {
    const tasks: any[] = [];

    messages.forEach((message, index) => {
      if (message.role === 'assistant') {
        // Look for TODO, FIXME, task indicators
        const taskPatterns = [
          /TODO:?\s*([^\n]+)/gi,
          /FIXME:?\s*([^\n]+)/gi,
          /I need to\s*([^\n.]+)/gi,
          /I will\s*([^\n.]+)/gi,
          /Next[,:\s]+([^\n.]+)/gi
        ];

        taskPatterns.forEach(pattern => {
          const matches = message.content.matchAll(pattern);
          for (const match of matches) {
            const description = match[1].trim();
            if (description.length > 10) { // Filter out very short matches
              tasks.push({
                id: uuidv4(),
                description,
                status: 'pending',
                created_at: message.timestamp,
                updated_at: message.timestamp,
                chat_session_id: sessionId,
                message_index: index,
                component: 'real_time_ingestion',
                priority: match[0].toLowerCase().includes('fixme') ? 'high' : 'medium',
                source: 'real_time_conversation'
              });
            }
          }
        });
      }
    });

    return tasks;
  }

  private extractErrors(messages: ConversationMessage[], sessionId: string): any[] {
    const errors: any[] = [];

    messages.forEach((message, index) => {
      // Look for error indicators
      const errorPatterns = [
        /ERROR:?\s*([^\n]+)/gi,
        /Error:?\s*([^\n]+)/gi,
        /Failed:?\s*([^\n]+)/gi,
        /Exception:?\s*([^\n]+)/gi,
        /❌\s*([^\n]+)/gi
      ];

      errorPatterns.forEach(pattern => {
        const matches = message.content.matchAll(pattern);
        for (const match of matches) {
          const errorMessage = match[1].trim();
          if (errorMessage.length > 5) {
            errors.push({
              id: uuidv4(),
              error_message: errorMessage,
              timestamp: message.timestamp,
              component: 'real_time_conversation',
              severity: 'medium',
              source: 'conversation_analysis',
              chat_session_id: sessionId,
              message_index: index
            });
          }
        }
      });
    });

    return errors;
  }

  private extractTopic(messages: ConversationMessage[]): string {
    // Try to determine conversation topic from first few messages
    const firstMessages = messages.slice(0, 3);
    const content = firstMessages.map(m => m.content).join(' ');

    // Simple topic extraction based on common words
    const words = content.toLowerCase().match(/\b\w+\b/g) || [];
    const commonTechWords = [
      'autobot', 'mcp', 'redis', 'docker', 'typescript', 'server', 'api',
      'frontend', 'backend', 'database', 'monitoring', 'error', 'fix', 'build'
    ];

    const topicWords = words.filter(word => commonTechWords.includes(word));

    if (topicWords.length > 0) {
      return `Real-time conversation about ${topicWords.slice(0, 3).join(', ')}`;
    }

    return `Real-time conversation (${new Date().toLocaleDateString()})`;
  }

  private extractParticipants(messages: ConversationMessage[]): string[] {
    const roles = [...new Set(messages.map(m => m.role))];
    return roles;
  }

  async shutdown() {
    console.log('[RealTimeIngestion] Shutting down real-time ingestion...');
    this.isRunning = false;

    // Stop watching files
    for (const [filePath, tail] of this.watchedFiles) {
      try {
        tail.unwatch();
        console.log(`[RealTimeIngestion] Stopped watching ${filePath}`);
      } catch (error) {
        console.log(`[RealTimeIngestion] Error stopping watch for ${filePath}:`, (error as Error).message);
      }
    }

    this.watchedFiles.clear();

    // Process any remaining buffered conversations
    for (const [sessionKey, messages] of this.conversationBuffer) {
      if (messages.length > 0) {
        await this.processBufferedConversation(sessionKey, messages);
      }
    }

    if (this.redis) {
      await this.redis.quit();
      this.redis = null;
    }
  }
}
