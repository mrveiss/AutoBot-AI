/**
 * AutoBot Code Intelligence - VSCode Extension
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Real-time code pattern detection, security analysis, and quick fixes
 * powered by AutoBot backend analytics engine.
 */

import * as vscode from 'vscode';
import axios, { AxiosInstance } from 'axios';

// Types for API responses
interface PatternMatch {
    rule_id: string;
    rule_name: string;
    severity: 'error' | 'warning' | 'info' | 'hint';
    message: string;
    line: number;
    column: number;
    end_line: number;
    end_column: number;
    category: string;
    suggestion?: string;
    quick_fix?: {
        title: string;
        replacement: string;
    };
}

interface AnalysisResult {
    success: boolean;
    file_path: string;
    language: string;
    patterns_found: PatternMatch[];
    analysis_time_ms: number;
    rules_checked: number;
}

interface QuickFixResult {
    success: boolean;
    original_code: string;
    fixed_code: string;
    rule_id: string;
    explanation: string;
}

interface HoverInfo {
    success: boolean;
    content: string;
    rule_id?: string;
    severity?: string;
    documentation_link?: string;
}

interface RuleInfo {
    id: string;
    name: string;
    description: string;
    severity: string;
    category: string;
    enabled: boolean;
}

// Extension state
let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;
let apiClient: AxiosInstance;
let analysisTimeout: NodeJS.Timeout | undefined;
let isAnalyzing = false;

/**
 * Extension activation point
 */
export function activate(context: vscode.ExtensionContext): void {
    console.log('AutoBot Code Intelligence is now active');

    // Initialize components
    initializeApiClient();
    initializeDiagnostics(context);
    initializeStatusBar(context);

    // Register commands
    registerCommands(context);

    // Register event handlers
    registerEventHandlers(context);

    // Initial analysis of open documents
    analyzeOpenDocuments();

    updateStatusBar('ready');
}

/**
 * Extension deactivation
 */
export function deactivate(): void {
    if (analysisTimeout) {
        clearTimeout(analysisTimeout);
    }
    diagnosticCollection.dispose();
    statusBarItem.dispose();
}

/**
 * Initialize the API client with configuration
 */
function initializeApiClient(): void {
    const config = vscode.workspace.getConfiguration('autobot');
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8001/api/ide');

    apiClient = axios.create({
        baseURL: serverUrl,
        timeout: 30000,
        headers: {
            'Content-Type': 'application/json',
        },
    });
}

/**
 * Initialize diagnostics collection
 */
function initializeDiagnostics(context: vscode.ExtensionContext): void {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('autobot');
    context.subscriptions.push(diagnosticCollection);
}

/**
 * Initialize status bar item
 */
function initializeStatusBar(context: vscode.ExtensionContext): void {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'autobot.showRules';
    context.subscriptions.push(statusBarItem);
    statusBarItem.show();
}

/**
 * Register all commands
 */
function registerCommands(context: vscode.ExtensionContext): void {
    // Analyze current file
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.analyze', async () => {
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                await analyzeDocument(editor.document, true);
            } else {
                vscode.window.showWarningMessage('No active editor to analyze');
            }
        })
    );

    // Analyze entire workspace
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.analyzeWorkspace', async () => {
            await analyzeWorkspace();
        })
    );

    // Toggle rule
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.toggleRule', async () => {
            await toggleRule();
        })
    );

    // Show available rules
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.showRules', async () => {
            await showRules();
        })
    );

    // Clear diagnostics
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.clearDiagnostics', () => {
            diagnosticCollection.clear();
            vscode.window.showInformationMessage('AutoBot diagnostics cleared');
        })
    );

    // Apply quick fix (internal command)
    context.subscriptions.push(
        vscode.commands.registerCommand('autobot.applyQuickFix', async (uri: vscode.Uri, range: vscode.Range, ruleId: string) => {
            await applyQuickFix(uri, range, ruleId);
        })
    );
}

/**
 * Register event handlers for real-time analysis
 */
function registerEventHandlers(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration('autobot');

    // Document change handler
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument((event) => {
            if (config.get<boolean>('enableRealTimeAnalysis', true)) {
                scheduleAnalysis(event.document);
            }
        })
    );

    // Document open handler
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument((document) => {
            if (config.get<boolean>('enableRealTimeAnalysis', true)) {
                scheduleAnalysis(document);
            }
        })
    );

    // Document save handler
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((document) => {
            analyzeDocument(document, false);
        })
    );

    // Document close handler
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument((document) => {
            diagnosticCollection.delete(document.uri);
        })
    );

    // Configuration change handler
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((event) => {
            if (event.affectsConfiguration('autobot')) {
                initializeApiClient();
            }
        })
    );

    // Register code action provider for quick fixes
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            [{ scheme: 'file', language: 'python' }, { scheme: 'file', language: 'typescript' }, { scheme: 'file', language: 'javascript' }],
            new AutoBotCodeActionProvider(),
            { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
        )
    );

    // Register hover provider
    context.subscriptions.push(
        vscode.languages.registerHoverProvider(
            [{ scheme: 'file', language: 'python' }, { scheme: 'file', language: 'typescript' }, { scheme: 'file', language: 'javascript' }],
            new AutoBotHoverProvider()
        )
    );
}

/**
 * Schedule analysis with debouncing
 */
function scheduleAnalysis(document: vscode.TextDocument): void {
    if (!isSupportedLanguage(document.languageId)) {
        return;
    }

    if (analysisTimeout) {
        clearTimeout(analysisTimeout);
    }

    const config = vscode.workspace.getConfiguration('autobot');
    const delay = config.get<number>('analysisDelay', 500);

    analysisTimeout = setTimeout(() => {
        analyzeDocument(document, false);
    }, delay);
}

/**
 * Analyze a single document
 */
async function analyzeDocument(document: vscode.TextDocument, showProgress: boolean): Promise<void> {
    if (!isSupportedLanguage(document.languageId)) {
        return;
    }

    if (isAnalyzing) {
        return;
    }

    isAnalyzing = true;
    updateStatusBar('analyzing');

    try {
        const config = vscode.workspace.getConfiguration('autobot');
        const disabledRules = config.get<string[]>('disabledRules', []);
        const enabledCategories = config.get<string[]>('enabledCategories', [
            'security', 'performance', 'code_quality', 'best_practice', 'error_prone'
        ]);
        const includeHints = config.get<boolean>('includeHints', true);

        const response = await apiClient.post<AnalysisResult>('/analyze', {
            code: document.getText(),
            language: document.languageId,
            file_path: document.fileName,
            enabled_categories: enabledCategories,
            disabled_rules: disabledRules,
            include_hints: includeHints,
        });

        if (response.data.success) {
            const diagnostics = createDiagnostics(response.data.patterns_found, document);
            diagnosticCollection.set(document.uri, diagnostics);

            const issueCount = response.data.patterns_found.length;
            updateStatusBar('ready', issueCount);

            if (showProgress) {
                if (issueCount > 0) {
                    vscode.window.showInformationMessage(
                        `AutoBot found ${issueCount} issue(s) in ${response.data.analysis_time_ms}ms`
                    );
                } else {
                    vscode.window.showInformationMessage('AutoBot: No issues found');
                }
            }
        }
    } catch (error) {
        handleApiError(error, 'Analysis failed');
        updateStatusBar('error');
    } finally {
        isAnalyzing = false;
    }
}

/**
 * Analyze all open documents
 */
function analyzeOpenDocuments(): void {
    vscode.workspace.textDocuments.forEach((document) => {
        if (isSupportedLanguage(document.languageId)) {
            analyzeDocument(document, false);
        }
    });
}

/**
 * Analyze entire workspace
 */
async function analyzeWorkspace(): Promise<void> {
    const config = vscode.workspace.getConfiguration('autobot');
    const enabledCategories = config.get<string[]>('enabledCategories', [
        'security', 'performance', 'code_quality', 'best_practice', 'error_prone'
    ]);

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: 'AutoBot: Analyzing Workspace',
            cancellable: true,
        },
        async (progress, token) => {
            const files = await vscode.workspace.findFiles(
                '**/*.{py,ts,js}',
                '**/node_modules/**',
                1000
            );

            let analyzed = 0;
            let totalIssues = 0;

            for (const file of files) {
                if (token.isCancellationRequested) {
                    break;
                }

                try {
                    const document = await vscode.workspace.openTextDocument(file);
                    await analyzeDocument(document, false);
                    analyzed++;

                    const diagnostics = diagnosticCollection.get(document.uri);
                    totalIssues += diagnostics?.length || 0;

                    progress.report({
                        increment: (100 / files.length),
                        message: `${analyzed}/${files.length} files`,
                    });
                } catch {
                    // Skip files that can't be opened
                }
            }

            vscode.window.showInformationMessage(
                `AutoBot: Analyzed ${analyzed} files, found ${totalIssues} issues`
            );
        }
    );
}

/**
 * Create diagnostics from pattern matches
 */
function createDiagnostics(patterns: PatternMatch[], document: vscode.TextDocument): vscode.Diagnostic[] {
    return patterns.map((pattern) => {
        const range = new vscode.Range(
            new vscode.Position(pattern.line - 1, pattern.column),
            new vscode.Position(pattern.end_line - 1, pattern.end_column)
        );

        const severity = mapSeverity(pattern.severity);
        const diagnostic = new vscode.Diagnostic(range, pattern.message, severity);

        diagnostic.source = 'AutoBot';
        diagnostic.code = pattern.rule_id;

        // Add related information if there's a suggestion
        if (pattern.suggestion) {
            diagnostic.relatedInformation = [
                new vscode.DiagnosticRelatedInformation(
                    new vscode.Location(document.uri, range),
                    `Suggestion: ${pattern.suggestion}`
                ),
            ];
        }

        // Store quick fix data in the diagnostic
        if (pattern.quick_fix) {
            (diagnostic as any).quickFix = pattern.quick_fix;
        }

        return diagnostic;
    });
}

/**
 * Map API severity to VSCode DiagnosticSeverity
 */
function mapSeverity(severity: string): vscode.DiagnosticSeverity {
    switch (severity) {
        case 'error':
            return vscode.DiagnosticSeverity.Error;
        case 'warning':
            return vscode.DiagnosticSeverity.Warning;
        case 'info':
            return vscode.DiagnosticSeverity.Information;
        case 'hint':
            return vscode.DiagnosticSeverity.Hint;
        default:
            return vscode.DiagnosticSeverity.Information;
    }
}

/**
 * Apply a quick fix from the backend
 */
async function applyQuickFix(uri: vscode.Uri, range: vscode.Range, ruleId: string): Promise<void> {
    try {
        const document = await vscode.workspace.openTextDocument(uri);
        const originalCode = document.getText(range);

        const response = await apiClient.post<QuickFixResult>('/quickfix', {
            code: originalCode,
            rule_id: ruleId,
            language: document.languageId,
            context: {
                file_path: document.fileName,
                line: range.start.line + 1,
            },
        });

        if (response.data.success && response.data.fixed_code !== originalCode) {
            const edit = new vscode.WorkspaceEdit();
            edit.replace(uri, range, response.data.fixed_code);
            await vscode.workspace.applyEdit(edit);

            vscode.window.showInformationMessage(`AutoBot: Applied fix for ${ruleId}`);

            // Re-analyze after fix
            await analyzeDocument(document, false);
        }
    } catch (error) {
        handleApiError(error, 'Quick fix failed');
    }
}

/**
 * Toggle a rule on/off
 */
async function toggleRule(): Promise<void> {
    try {
        const response = await apiClient.get<{ rules: RuleInfo[] }>('/rules');
        const rules = response.data.rules;

        const items = rules.map((rule) => ({
            label: `${rule.enabled ? '$(check)' : '$(x)'} ${rule.name}`,
            description: rule.category,
            detail: rule.description,
            rule: rule,
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select a rule to toggle',
            matchOnDescription: true,
            matchOnDetail: true,
        });

        if (selected) {
            const config = vscode.workspace.getConfiguration('autobot');
            const disabledRules = config.get<string[]>('disabledRules', []);

            if (disabledRules.includes(selected.rule.id)) {
                // Enable the rule
                const newDisabled = disabledRules.filter((r) => r !== selected.rule.id);
                await config.update('disabledRules', newDisabled, vscode.ConfigurationTarget.Workspace);
                vscode.window.showInformationMessage(`AutoBot: Enabled rule "${selected.rule.name}"`);
            } else {
                // Disable the rule
                disabledRules.push(selected.rule.id);
                await config.update('disabledRules', disabledRules, vscode.ConfigurationTarget.Workspace);
                vscode.window.showInformationMessage(`AutoBot: Disabled rule "${selected.rule.name}"`);
            }

            // Re-analyze open documents
            analyzeOpenDocuments();
        }
    } catch (error) {
        handleApiError(error, 'Failed to load rules');
    }
}

/**
 * Show available rules in a webview panel
 */
async function showRules(): Promise<void> {
    try {
        const response = await apiClient.get<{ rules: RuleInfo[] }>('/rules');
        const rules = response.data.rules;

        const config = vscode.workspace.getConfiguration('autobot');
        const disabledRules = config.get<string[]>('disabledRules', []);

        const categories = [...new Set(rules.map((r) => r.category))];

        let markdown = '# AutoBot Rules\n\n';

        for (const category of categories) {
            markdown += `## ${category}\n\n`;
            const categoryRules = rules.filter((r) => r.category === category);

            for (const rule of categoryRules) {
                const status = disabledRules.includes(rule.id) ? '❌ Disabled' : '✅ Enabled';
                markdown += `### ${rule.name} (${rule.severity})\n`;
                markdown += `**ID:** \`${rule.id}\` | **Status:** ${status}\n\n`;
                markdown += `${rule.description}\n\n`;
            }
        }

        const doc = await vscode.workspace.openTextDocument({
            content: markdown,
            language: 'markdown',
        });

        await vscode.window.showTextDocument(doc, { preview: true });
    } catch (error) {
        handleApiError(error, 'Failed to load rules');
    }
}

/**
 * Update status bar item
 */
function updateStatusBar(status: 'ready' | 'analyzing' | 'error', issueCount?: number): void {
    switch (status) {
        case 'ready':
            if (issueCount !== undefined && issueCount > 0) {
                statusBarItem.text = `$(warning) AutoBot: ${issueCount} issues`;
                statusBarItem.tooltip = `AutoBot found ${issueCount} issue(s). Click to see rules.`;
            } else {
                statusBarItem.text = '$(check) AutoBot';
                statusBarItem.tooltip = 'AutoBot Code Intelligence - No issues';
            }
            statusBarItem.backgroundColor = undefined;
            break;
        case 'analyzing':
            statusBarItem.text = '$(sync~spin) AutoBot';
            statusBarItem.tooltip = 'AutoBot is analyzing...';
            statusBarItem.backgroundColor = undefined;
            break;
        case 'error':
            statusBarItem.text = '$(error) AutoBot';
            statusBarItem.tooltip = 'AutoBot encountered an error. Click for details.';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            break;
    }
}

/**
 * Check if language is supported
 */
function isSupportedLanguage(languageId: string): boolean {
    return ['python', 'typescript', 'javascript', 'typescriptreact', 'javascriptreact'].includes(languageId);
}

/**
 * Handle API errors
 */
function handleApiError(error: unknown, context: string): void {
    let message = context;

    if (axios.isAxiosError(error)) {
        if (error.response) {
            message = `${context}: ${error.response.data?.error || error.response.statusText}`;
        } else if (error.code === 'ECONNREFUSED') {
            message = `${context}: Cannot connect to AutoBot server. Is it running?`;
        } else {
            message = `${context}: ${error.message}`;
        }
    }

    console.error('AutoBot error:', error);
    vscode.window.showErrorMessage(message);
}

/**
 * Code Action Provider for quick fixes
 */
class AutoBotCodeActionProvider implements vscode.CodeActionProvider {
    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        context: vscode.CodeActionContext
    ): vscode.CodeAction[] {
        const actions: vscode.CodeAction[] = [];

        for (const diagnostic of context.diagnostics) {
            if (diagnostic.source !== 'AutoBot') {
                continue;
            }

            const quickFix = (diagnostic as any).quickFix;
            if (quickFix) {
                const action = new vscode.CodeAction(
                    `AutoBot: ${quickFix.title}`,
                    vscode.CodeActionKind.QuickFix
                );

                action.diagnostics = [diagnostic];
                action.isPreferred = true;

                // Create workspace edit for inline fix
                action.edit = new vscode.WorkspaceEdit();
                action.edit.replace(document.uri, diagnostic.range, quickFix.replacement);

                actions.push(action);
            }

            // Add "Apply server fix" action
            const serverFix = new vscode.CodeAction(
                `AutoBot: Apply AI-powered fix for ${diagnostic.code}`,
                vscode.CodeActionKind.QuickFix
            );

            serverFix.diagnostics = [diagnostic];
            serverFix.command = {
                command: 'autobot.applyQuickFix',
                title: 'Apply AutoBot Fix',
                arguments: [document.uri, diagnostic.range, diagnostic.code as string],
            };

            actions.push(serverFix);

            // Add "Disable this rule" action
            const disableRule = new vscode.CodeAction(
                `AutoBot: Disable rule "${diagnostic.code}"`,
                vscode.CodeActionKind.QuickFix
            );

            disableRule.diagnostics = [diagnostic];
            disableRule.command = {
                command: 'autobot.toggleRule',
                title: 'Toggle Rule',
            };

            actions.push(disableRule);
        }

        return actions;
    }
}

/**
 * Hover Provider for additional information
 */
class AutoBotHoverProvider implements vscode.HoverProvider {
    async provideHover(
        document: vscode.TextDocument,
        position: vscode.Position
    ): Promise<vscode.Hover | undefined> {
        // Check if there's a diagnostic at this position
        const diagnostics = diagnosticCollection.get(document.uri);
        if (!diagnostics) {
            return undefined;
        }

        const diagnostic = diagnostics.find((d) => d.range.contains(position) && d.source === 'AutoBot');
        if (!diagnostic) {
            return undefined;
        }

        try {
            const response = await apiClient.post<HoverInfo>('/hover', {
                rule_id: diagnostic.code,
                code: document.getText(diagnostic.range),
                language: document.languageId,
            });

            if (response.data.success) {
                const markdown = new vscode.MarkdownString();
                markdown.appendMarkdown(`**AutoBot: ${diagnostic.code}**\n\n`);
                markdown.appendMarkdown(response.data.content);

                if (response.data.documentation_link) {
                    markdown.appendMarkdown(`\n\n[Learn more](${response.data.documentation_link})`);
                }

                markdown.isTrusted = true;
                return new vscode.Hover(markdown);
            }
        } catch {
            // Fall back to basic hover
        }

        // Basic hover with diagnostic info
        const markdown = new vscode.MarkdownString();
        markdown.appendMarkdown(`**AutoBot: ${diagnostic.code}**\n\n`);
        markdown.appendMarkdown(diagnostic.message);

        return new vscode.Hover(markdown);
    }
}
