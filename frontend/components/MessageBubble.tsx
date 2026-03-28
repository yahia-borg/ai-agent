"use client";

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, Image as ImageIcon, FileText } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
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

  if (!message.content && (!message.attachments || message.attachments.length === 0)) {
    return null;
  }

  return (
    <div
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''} animate-in fade-in slide-in-from-bottom-2 duration-300`}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <Avatar className="h-8 w-8 shrink-0 mt-0.5">
        <AvatarFallback
          className={
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
          }
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 shadow-sm text-sm leading-relaxed ${
          isUser
            ? 'bg-primary text-primary-foreground rounded-tr-sm'
            : 'bg-card text-card-foreground border border-border rounded-tl-sm'
        }`}
      >
        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="mb-2 space-y-1.5">
            {message.attachments.map((attachment, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 p-2 bg-black/10 dark:bg-white/10 rounded-lg"
              >
                {attachment.type === 'image' ? (
                  <>
                    <ImageIcon className="h-4 w-4" />
                    <img
                      src={attachment.url}
                      alt={attachment.name}
                      className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
                    />
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4" />
                    <span className="text-sm truncate">{attachment.name}</span>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message content */}
        <div
          className={`message-content prose prose-sm max-w-none ${
            isUser ? 'prose-invert' : 'dark:prose-invert'
          }`}
          dir={isRTL ? 'rtl' : 'ltr'}
        >
          <ReactMarkdown
            components={{
              a: ({ node, ...props }) => {
                const href = props.href || '';
                const isRelativeApi = href.startsWith('/api/');
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
                const fullHref = isRelativeApi ? `${apiUrl}${href}` : href;
                return (
                  <a
                    {...props}
                    href={fullHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={isUser ? 'text-primary-foreground underline' : 'text-primary hover:underline'}
                  >
                    {props.children}
                  </a>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
