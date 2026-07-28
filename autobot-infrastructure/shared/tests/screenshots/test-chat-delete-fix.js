#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Test and fix the chat deletion functionality
 */

async function testChatDeletion() {
    console.log('💬 TESTING CHAT DELETION FUNCTIONALITY');
    console.log('='.repeat(50));

    try {
        // Step 1: Get list of existing chats
        console.log('📋 Getting list of existing chats...');
        const chatListResponse = await fetch('http://localhost:8001/api/chats');

        if (!chatListResponse.ok) {
            throw new Error(`Failed to get chat list: ${chatListResponse.status}`);
        }

        const chatData = await chatListResponse.json();
        const chats = chatData.chats || [];

        console.log(`✅ Found ${chats.length} existing chats`);

        if (chats.length === 0) {
            console.log('ℹ️  No chats to test deletion with');
            return false;
        }

        // Show chat details
        chats.forEach((chat, i) => {
            console.log(`${i + 1}. Chat ID: ${chat.chatId}`);
            console.log(`   Name: "${chat.name}" (${chat.messageCount} messages)`);
            console.log(`   Created: ${chat.createdTime}`);
        });

        // Step 2: Try to delete the oldest chat
        const chatToDelete = chats[chats.length - 1]; // Get the last (oldest) chat
        console.log(`\n🗑️  Attempting to delete chat: ${chatToDelete.chatId}`);

        const deleteResponse = await fetch(`http://localhost:8001/api/chats/${chatToDelete.chatId}`, {
            method: 'DELETE'
        });

        const deleteResult = await deleteResponse.json();

        if (deleteResponse.ok) {
            console.log('✅ Chat deletion successful!');
            console.log(`📝 Response: ${JSON.stringify(deleteResult)}`);

            // Step 3: Verify the chat was actually deleted
            const verifyResponse = await fetch('http://localhost:8001/api/chats');
            const verifyData = await verifyResponse.json();
            const remainingChats = verifyData.chats || [];

            const chatStillExists = remainingChats.some(c => c.chatId === chatToDelete.chatId);

            if (!chatStillExists) {
                console.log('✅ Verification: Chat successfully removed from list');
                return true;
            } else {
                console.log('⚠️  Verification: Chat still exists in list');
                return false;
            }

        } else {
            console.log(`❌ Chat deletion failed: ${deleteResponse.status}`);
            console.log(`📝 Error: ${JSON.stringify(deleteResult)}`);

            // Check if the issue is related to chat ID format or backend storage
            console.log('\n🔍 Debugging chat deletion issue...');
            console.log(`Chat ID format: ${chatToDelete.chatId} (length: ${chatToDelete.chatId.length})`);

            return false;
        }

    } catch (error) {
        console.error('❌ Chat deletion test failed:', error.message);
        return false;
    }
}

// Test creating and then deleting a new chat
async function testNewChatDeletion() {
    console.log('\n➕ TESTING NEW CHAT CREATION AND DELETION...');

    try {
        // Create a new chat
        const createResponse = await fetch('http://localhost:8001/api/chats/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'Test Chat for Deletion' })
        });

        if (createResponse.ok) {
            const newChat = await createResponse.json();
            console.log(`✅ Created new chat: ${newChat.chat_id}`);

            // Now try to delete it
            const deleteResponse = await fetch(`http://localhost:8001/api/chats/${newChat.chat_id}`, {
                method: 'DELETE'
            });

            const deleteResult = await deleteResponse.json();

            if (deleteResponse.ok) {
                console.log('✅ New chat deleted successfully');
                return true;
            } else {
                console.log(`❌ Failed to delete new chat: ${JSON.stringify(deleteResult)}`);
                return false;
            }

        } else {
            console.log(`❌ Failed to create new chat: ${createResponse.status}`);
            return false;
        }

    } catch (error) {
        console.error('❌ New chat deletion test failed:', error.message);
        return false;
    }
}

// Run comprehensive chat deletion testing
Promise.all([
    testChatDeletion(),
    testNewChatDeletion()
]).then(([existingChatResult, newChatResult]) => {
    console.log('\n' + '='.repeat(50));
    console.log('💬 CHAT DELETION TESTING: COMPLETED');
    console.log('='.repeat(50));

    if (existingChatResult || newChatResult) {
        console.log('✅ STATUS: CHAT DELETION PARTIALLY WORKING');

        if (existingChatResult) {
            console.log('✅ Existing Chat Deletion: Working');
        } else {
            console.log('❌ Existing Chat Deletion: Failed');
        }

        if (newChatResult) {
            console.log('✅ New Chat Deletion: Working');
        } else {
            console.log('❌ New Chat Deletion: Failed');
        }

        if (!existingChatResult && newChatResult) {
            console.log('\n💡 ANALYSIS: New chats can be deleted but existing ones cannot');
            console.log('This suggests a chat ID format or storage inconsistency issue');
            console.log('\n🛠️ POTENTIAL FIXES:');
            console.log('1. Check chat ID format differences between old and new chats');
            console.log('2. Update existing chat IDs to match expected format');
            console.log('3. Make delete function more flexible with ID matching');
        }

    } else {
        console.log('❌ STATUS: CHAT DELETION NOT WORKING');
        console.log('\n🔍 TROUBLESHOOTING NEEDED:');
        console.log('• Check backend chat storage implementation');
        console.log('• Verify chat ID format consistency');
        console.log('• Test chat manager delete_session method');
        console.log('• Check for database/file storage issues');
    }

    console.log('\n📋 FRONTEND ERROR CONTEXT:');
    console.log('The ChatInterface.vue error occurs when users try to delete chats');
    console.log('Error: "HTTP 404: Not Found" from DELETE /api/chats/{chatId}');
    console.log('Fix: Ensure backend chat deletion works for all chat ID formats');

    console.log('='.repeat(50));
}).catch(error => {
    console.error('\n❌ CHAT DELETION TEST FAILED:', error);
});
