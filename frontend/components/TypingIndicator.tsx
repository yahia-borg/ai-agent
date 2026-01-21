"use client";

import React from 'react';
import { Loader2, Bot } from 'lucide-react';

export default function TypingIndicator() {
    return (
        <div className="flex gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-md">
                <Loader2 className="w-5 h-5 text-white animate-spin" />
            </div>
            <div className="bg-white dark:bg-slate-800 px-5 py-4 rounded-3xl rounded-tl-sm border border-slate-200 dark:border-slate-700 shadow-md">
                <div className="flex items-center gap-2">
                    <span className="text-slate-600 dark:text-slate-300 text-sm font-medium">Analyzing your request</span>
                    <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                        <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                        <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                    </div>
                </div>
            </div>
        </div>
    );
}

