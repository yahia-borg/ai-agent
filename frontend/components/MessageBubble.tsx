"use client";

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, Image as ImageIcon, FileText } from 'lucide-react';
import { detectLanguage } from '@/utils/language';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    attachments?: Array<{
        type: 'image' | 'file';
        url: string;
        name: string;
    }>;
}

interface MessageBubbleProps {
    message: Message;
    index: number;
}

export default function MessageBubble({ message, index }: MessageBubbleProps) {
    const isUser = message.role === 'user';
    const detectedLang = detectLanguage(message.content);
    const isRTL = detectedLang === 'ar';

    // Don't render empty messages (prevents empty bubbles during streaming start)
    if (!message.content && (!message.attachments || message.attachments.length === 0)) {
        return null;
    }

    return (
        <div
            className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''} animate-in fade-in slide-in-from-bottom-2 duration-300`}
            dir={isRTL ? 'rtl' : 'ltr'}
        >
            {/* Avatar */}
            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-md ${isUser
                    ? 'bg-gradient-to-br from-indigo-500 to-indigo-600'
                    : 'bg-gradient-to-br from-blue-500 to-blue-600'
                }`}>
                {isUser ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
            </div>

            {/* Message bubble */}
            <div className={`max-w-[75%] rounded-3xl px-5 py-4 shadow-md ${isUser
                    ? 'bg-gradient-to-br from-indigo-600 to-indigo-700 text-white rounded-tr-sm'
                    : 'bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 rounded-tl-sm border border-slate-200 dark:border-slate-700'
                }`}>
                {/* Attachments */}
                {message.attachments && message.attachments.length > 0 && (
                    <div className="mb-3 space-y-2">
                        {message.attachments.map((attachment, idx) => (
                            <div key={idx} className="flex items-center gap-2 p-2 bg-black/10 dark:bg-white/10 rounded-lg">
                                {attachment.type === 'image' ? (
                                    <>
                                        <ImageIcon className="w-4 h-4" />
                                        <img
                                            src={attachment.url}
                                            alt={attachment.name}
                                            className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
                                        />
                                    </>
                                ) : (
                                    <>
                                        <FileText className="w-4 h-4" />
                                        <span className="text-sm truncate">{attachment.name}</span>
                                    </>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Message content */}
                <div className={`prose prose-sm ${isUser ? 'prose-invert' : 'dark:prose-invert'} max-w-none leading-relaxed`}>
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                </div>
            </div>
        </div>
    );
}

