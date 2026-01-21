"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Paperclip, X, Image as ImageIcon } from 'lucide-react';
import axios from 'axios';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import DownloadButtons from './DownloadButtons';
import { detectLanguage } from '@/utils/language';

interface Attachment {
    type: 'image' | 'file';
    file: File;
    url: string;
    name: string;
}

interface Message {
    role: 'user' | 'assistant';
    content: string;
    attachments?: Array<{
        type: 'image' | 'file';
        url: string;
        name: string;
    }>;
}

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        { role: 'assistant', content: 'Hello! I am your AI Construction Consultant. How can I help you regarding your project cost or quotation?' }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [quotationId, setQuotationId] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const textInputRef = useRef<HTMLInputElement>(null);
    const assistantMessageRef = useRef<number>(-1);

    // Generate new session ID
    const generateSessionId = () => {
        return `session-${Math.random().toString(36).substring(2, 15)}`;
    };

    // Load conversation history from localStorage
    useEffect(() => {
        // Generate new session_id on page load (fresh session)
        const newSessionId = generateSessionId();
        setSessionId(newSessionId);
        localStorage.setItem('chat_session_id', newSessionId);

        // IMPORTANT: We do NOT load quotation_id from localStorage here
        // fresh tabs/page reloads should start with a clean state
        // to avoid linking new sessions to old project data.
        setQuotationId(null);
    }, []);

    // Handle "New Chat" button
    const handleNewChat = () => {
        const newSessionId = generateSessionId();
        setSessionId(newSessionId);
        setMessages([{ role: 'assistant', content: 'Hello! I am your AI Construction Consultant. How can I help you regarding your project cost or quotation?' }]);
        setQuotationId(null);
        localStorage.setItem('chat_session_id', newSessionId);
        localStorage.removeItem('quotation_id');
        localStorage.removeItem('chat_messages');
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        files.forEach(file => {
            const url = URL.createObjectURL(file);
            const attachment: Attachment = {
                type: file.type.startsWith('image/') ? 'image' : 'file',
                file,
                url,
                name: file.name
            };
            setAttachments(prev => [...prev, attachment]);
        });
        // Reset input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const removeAttachment = (index: number) => {
        const attachment = attachments[index];
        URL.revokeObjectURL(attachment.url);
        setAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const sendMessage = async () => {
        if (!input.trim() && attachments.length === 0) return;

        const userMsg: Message = {
            role: 'user',
            content: input,
            attachments: attachments.map(att => ({
                type: att.type,
                url: att.url,
                name: att.name
            }))
        };

        const currentInput = input;
        setInput('');
        const currentAttachments = [...attachments];
        setAttachments([]);

        // Build history from current messages (before adding user message)
        // Format: only role and content (backend expects Dict[str, str])
        // Ensure content is always a string and filter out any invalid messages
        const historyForRequest = messages
            .filter(msg => msg.role === 'user' || msg.role === 'assistant')
            .map(msg => ({
                role: msg.role,
                content: String(msg.content || '')
            }));

        // Add user message to UI state
        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

            // If there are attachments, use regular POST (multipart/form-data doesn't work with SSE)
            if (currentAttachments.length > 0) {
                const formData = new FormData();
                formData.append('message', currentInput);
                // Send history (current messages, which doesn't include the user message we just added)
                formData.append('history', JSON.stringify(historyForRequest));
                if (sessionId) {
                    formData.append('session_id', sessionId);
                }
                if (quotationId) {
                    formData.append('quotation_id', quotationId);
                }
                currentAttachments.forEach((att) => {
                    formData.append('files', att.file);
                });

                const response = await axios.post(`${apiUrl}/api/v1/chat`, formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                    timeout: 120000
                });

                const aiMsg: Message = { role: 'assistant', content: response.data.response };
                setMessages(prev => [...prev, aiMsg]);

                // Store quotation_id if provided (for quotation linking)
                if (response.data.quotation_id) {
                    setQuotationId(response.data.quotation_id);
                    localStorage.setItem('quotation_id', response.data.quotation_id);
                }
            } else {
                // Use streaming endpoint for token-by-token response
                const response = await fetch(`${apiUrl}/api/v1/chat/stream`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: currentInput,
                        // Send history (current messages, which doesn't include the user message we just added)
                        history: historyForRequest,
                        session_id: sessionId,
                        quotation_id: quotationId
                    })
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error(`HTTP error! status: ${response.status}, body:`, errorText);
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                // Create assistant message and capture its index using functional update
                setMessages(prev => {
                    assistantMessageRef.current = prev.length;
                    return [...prev, { role: 'assistant', content: '' }];
                });

                const reader = response.body?.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let fullResponse = '';

                if (reader) {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop() || '';

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.slice(6));

                                    if (data.type === 'content') {
                                        fullResponse += data.content;
                                        // Update the message in real-time using the ref index
                                        setMessages(prev => {
                                            const updated = [...prev];
                                            const idx = assistantMessageRef.current;
                                            if (idx >= 0 && idx < updated.length && updated[idx].role === 'assistant') {
                                                updated[idx] = {
                                                    ...updated[idx],
                                                    content: fullResponse
                                                };
                                            }
                                            return updated;
                                        });
                                    } else if (data.type === 'done') {
                                        if (data.quotation_id) {
                                            setQuotationId(data.quotation_id);
                                            localStorage.setItem('quotation_id', data.quotation_id);
                                        }
                                    } else if (data.type === 'error') {
                                        throw new Error(data.content);
                                    }
                                } catch (e) {
                                    console.error('Error parsing SSE data:', e, 'Line:', line);
                                }
                            }
                        }
                    }
                }
            }
        } catch (error: any) {
            console.error("Error sending message:", error);
            let errorMessage = "Sorry, I encountered an error connecting to the server.";
            if (error?.message?.includes('422')) {
                errorMessage = "Invalid request format. Please try again.";
            } else if (error?.message?.includes('status')) {
                errorMessage = `Server error: ${error.message}`;
            }
            const errorMsg: Message = { role: 'assistant', content: errorMessage };
            setMessages(prev => [...prev, errorMsg]);
            // Reset assistant message ref on error
            assistantMessageRef.current = -1;
        } finally {
            setIsLoading(false);
            // Auto-focus the input field after message is sent
            setTimeout(() => {
                textInputRef.current?.focus();
            }, 100);
        }
    };

    return (
        <div className="flex flex-col h-[85vh] w-full max-w-5xl mx-auto bg-white dark:bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800">
            {/* Header - Minimal style like ChatGPT/Claude */}
            <div className="bg-white dark:bg-slate-900 px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
                        <Bot className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-lg font-semibold text-slate-900 dark:text-white">BuildAI</h1>
                </div>
                <button
                    onClick={handleNewChat}
                    className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors flex items-center gap-2"
                    title="Start a new conversation"
                >
                    <span>+</span>
                    <span>New Chat</span>
                </button>
            </div>

            {/* Quotation Status Banner */}
            {quotationId && (
                <div className="bg-blue-50 dark:bg-slate-800/50 border-b border-blue-100 dark:border-slate-700 px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                        <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                            Quotation Ready: {quotationId.substring(0, 12)}...
                        </span>
                    </div>
                    <DownloadButtons quotationId={quotationId} />
                </div>
            )}

            {/* Messages - MD3 spacing: 24dp padding, 16dp gap */}
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 bg-gradient-to-b from-slate-50 to-white dark:from-slate-900 dark:to-slate-950">
                {messages.map((msg, idx) => (
                    <MessageBubble key={idx} message={msg} index={idx} />
                ))}
                {isLoading && <TypingIndicator />}
                <div ref={messagesEndRef} />
            </div>

            {/* Input area - MD3 spacing: 20dp padding */}
            <div className="px-6 py-5 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-700 shadow-inner">
                {/* Attachments preview */}
                {attachments.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-2">
                        {attachments.map((att, idx) => (
                            <div key={idx} className="flex items-center gap-2 px-3 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg">
                                {att.type === 'image' ? (
                                    <ImageIcon className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                                ) : (
                                    <Paperclip className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                                )}
                                <span className="text-sm text-slate-700 dark:text-slate-300 truncate max-w-[150px]">{att.name}</span>
                                <button
                                    onClick={() => removeAttachment(idx)}
                                    className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}

                <div className="flex gap-3 items-center">
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileSelect}
                        accept="image/*,.pdf,.doc,.docx"
                        multiple
                        className="hidden"
                        id="file-input"
                    />
                    <label
                        htmlFor="file-input"
                        className="p-4 rounded-2xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer transition-colors"
                    >
                        <Paperclip className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                    </label>
                    <input
                        ref={textInputRef}
                        type="text"
                        dir="auto"
                        inputMode="text"
                        lang="auto"
                        className="flex-1 px-5 py-4 rounded-2xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:border-blue-500 dark:focus:border-blue-400 focus:ring-4 focus:ring-blue-500/10 text-slate-900 dark:text-white placeholder-slate-500 dark:placeholder-slate-400 outline-none transition-all duration-200 text-base"
                        placeholder="Describe your construction project..."
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                        disabled={isLoading}
                        autoFocus
                    />
                    <button
                        onClick={sendMessage}
                        disabled={isLoading || (!input.trim() && attachments.length === 0)}
                        className="px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed text-white rounded-2xl flex items-center gap-2 transition-all duration-200 shadow-lg hover:shadow-xl disabled:shadow-none font-medium group"
                    >
                        <Send className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
                        <span className="hidden sm:inline">Send</span>
                    </button>
                </div>
                <p className="text-center text-xs text-slate-500 dark:text-slate-400 mt-3 font-medium">
                    💡 AI-powered estimates • Always verify critical information
                </p>
            </div>
        </div>
    );
}
