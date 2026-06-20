"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, X, Image as ImageIcon } from 'lucide-react';
import axios from 'axios';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import DownloadButtons from './DownloadButtons';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

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

const WELCOME_MSG: Message = {
  role: 'assistant',
  content:
    'أهلاً! أنا مستشارك الذكي لتشطيبات البناء. قولي إيه اللي عايز تعمله وهنعملك عرض سعر دلوقتي 💪',
};

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MSG]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [quotationId, setQuotationId] = useState<string | null>(null);
  const [quotationCompleted, setQuotationCompleted] = useState<boolean>(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textInputRef = useRef<HTMLTextAreaElement>(null);
  const assistantMessageRef = useRef<number>(-1);

  const generateSessionId = () => `session-${Math.random().toString(36).substring(2, 15)}`;

  useEffect(() => {
    const newSessionId = generateSessionId();
    setSessionId(newSessionId);
    localStorage.setItem('chat_session_id', newSessionId);
    setQuotationId(null);
  }, []);

  const handleNewChat = () => {
    const newSessionId = generateSessionId();
    setSessionId(newSessionId);
    setMessages([WELCOME_MSG]);
    setQuotationId(null);
    setQuotationCompleted(false);
    localStorage.setItem('chat_session_id', newSessionId);
    localStorage.removeItem('quotation_id');
    localStorage.removeItem('chat_messages');
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      const url = URL.createObjectURL(file);
      setAttachments((prev) => [
        ...prev,
        { type: file.type.startsWith('image/') ? 'image' : 'file', file, url, name: file.name },
      ]);
    });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (index: number) => {
    URL.revokeObjectURL(attachments[index].url);
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const sendMessage = async () => {
    if (!input.trim() && attachments.length === 0) return;

    const userMsg: Message = {
      role: 'user',
      content: input,
      attachments: attachments.map((a) => ({ type: a.type, url: a.url, name: a.name })),
    };

    const currentInput = input;
    const currentAttachments = [...attachments];
    setInput('');
    setAttachments([]);

    const historyForRequest = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role, content: String(m.content || '') }));

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

      if (currentAttachments.length > 0) {
        const formData = new FormData();
        formData.append('message', currentInput);
        formData.append('history', JSON.stringify(historyForRequest));
        if (sessionId) formData.append('session_id', sessionId);
        if (quotationId) formData.append('quotation_id', quotationId);
        currentAttachments.forEach((a) => formData.append('files', a.file));

        const response = await axios.post(`${apiUrl}/api/v1/chat`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000,
        });

        setMessages((prev) => [...prev, { role: 'assistant', content: response.data.response }]);
        if (response.data.quotation_id) {
          setQuotationId(response.data.quotation_id);
          localStorage.setItem('quotation_id', response.data.quotation_id);
        }
      } else {
        const response = await fetch(`${apiUrl}/api/v1/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: currentInput,
            history: historyForRequest,
            session_id: sessionId,
            quotation_id: quotationId,
          }),
        });

        if (!response.ok) {
          const errorText = await response.text();
          console.error(`HTTP error! status: ${response.status}, body:`, errorText);
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        setMessages((prev) => {
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
                    setMessages((prev) => {
                      const updated = [...prev];
                      const idx = assistantMessageRef.current;
                      if (idx >= 0 && idx < updated.length && updated[idx].role === 'assistant') {
                        updated[idx] = { ...updated[idx], content: fullResponse };
                      }
                      return updated;
                    });
                  } else if (data.type === 'done') {
                    if (data.quotation_id) {
                      setQuotationId(data.quotation_id);
                      localStorage.setItem('quotation_id', data.quotation_id);
                      if (data.quotation_status === 'completed') {
                        setQuotationCompleted(true);
                      }
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
      console.error('Error sending message:', error);
      let errorMessage = 'Sorry, I encountered an error connecting to the server.';
      if (error?.message?.includes('422')) errorMessage = 'Invalid request format. Please try again.';
      else if (error?.message?.includes('status')) errorMessage = `Server error: ${error.message}`;
      setMessages((prev) => [...prev, { role: 'assistant', content: errorMessage }]);
      assistantMessageRef.current = -1;
    } finally {
      setIsLoading(false);
      setTimeout(() => textInputRef.current?.focus(), 100);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-[92vh] w-full bg-card rounded-2xl border border-border shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-primary-foreground text-xs font-bold">B</span>
          </div>
          <span className="font-semibold text-sm text-foreground">BuildAI</span>
        </div>
        <Button variant="outline" size="sm" onClick={handleNewChat} className="gap-1.5 h-8 text-xs">
          <span>+</span>
          New Chat
        </Button>
      </div>

      {/* Quotation ready banner — only shown once cost calculation is complete */}
      {quotationCompleted && quotationId && (
        <>
          <div className="px-5 py-2.5 bg-primary/5 border-b border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
              <span className="text-xs font-medium text-primary">
                Quotation ready · {quotationId.substring(0, 10)}…
              </span>
            </div>
            <DownloadButtons quotationId={quotationId} />
          </div>
        </>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 px-5 py-5">
        <div className="space-y-5">
          {messages.map((msg, idx) => (
            <MessageBubble key={idx} message={msg} index={idx} />
          ))}
          {isLoading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="px-4 pb-4 pt-3 border-t border-border shrink-0">
        {/* Attachments */}
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachments.map((att, idx) => (
              <div
                key={idx}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-muted rounded-lg text-xs text-muted-foreground"
              >
                {att.type === 'image' ? (
                  <ImageIcon className="h-3.5 w-3.5" />
                ) : (
                  <Paperclip className="h-3.5 w-3.5" />
                )}
                <span className="truncate max-w-[120px]">{att.name}</span>
                <button
                  onClick={() => removeAttachment(idx)}
                  className="text-muted-foreground hover:text-foreground ml-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2 bg-muted rounded-xl border border-border px-3 py-2 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
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
            className="text-muted-foreground hover:text-foreground cursor-pointer p-1 transition-colors shrink-0"
          >
            <Paperclip className="h-4 w-4" />
          </label>

          <textarea
            ref={textInputRef}
            dir="auto"
            rows={1}
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none resize-none min-h-[24px] max-h-[120px] py-1 leading-relaxed"
            placeholder="اكتب تفاصيل مشروعك هنا…"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = `${e.target.scrollHeight}px`;
            }}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            autoFocus
          />

          <Button
            size="icon"
            className="h-8 w-8 shrink-0 rounded-lg"
            onClick={sendMessage}
            disabled={isLoading || (!input.trim() && attachments.length === 0)}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>

        <p className="text-center text-[11px] text-muted-foreground mt-2" dir="rtl">
          تقديرات بالذكاء الاصطناعي · تحقق دايمًا من المعلومات المهمة
        </p>
      </div>
    </div>
  );
}
