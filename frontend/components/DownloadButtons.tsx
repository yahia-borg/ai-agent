"use client";

import React, { useState } from 'react';
import { Download, FileText, FileSpreadsheet, Archive, Loader2 } from 'lucide-react';
import axios from 'axios';

interface DownloadButtonsProps {
    quotationId: string;
    disabled?: boolean;
}

export default function DownloadButtons({ quotationId, disabled = false }: DownloadButtonsProps) {
    const [downloading, setDownloading] = useState<string | null>(null);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

    const handleDownload = async (format: 'pdf' | 'excel' | 'both') => {
        if (disabled || downloading) return;

        setDownloading(format);
        try {
            // Use unified download endpoint with format query parameter
            const endpoint = `${apiUrl}/api/v1/quotations/${quotationId}/download?format=${format}`;
            
            const response = await axios.get(endpoint, {
                responseType: 'blob',
            });

            // Create download link
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            
            const extension = format === 'both' ? 'zip' : format === 'pdf' ? 'pdf' : 'xlsx';
            link.setAttribute('download', `quotation_${quotationId}.${extension}`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error(`Error downloading ${format}:`, error);
            alert(`Failed to download ${format}. Please try again.`);
        } finally {
            setDownloading(null);
        }
    };

    return (
        <div className="flex flex-wrap gap-3">
            <button
                onClick={() => handleDownload('pdf')}
                disabled={disabled || downloading !== null}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-lg transition-colors shadow-md hover:shadow-lg"
            >
                {downloading === 'pdf' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <FileText className="w-4 h-4" />
                )}
                <span>Download PDF</span>
            </button>

            <button
                onClick={() => handleDownload('excel')}
                disabled={disabled || downloading !== null}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-lg transition-colors shadow-md hover:shadow-lg"
            >
                {downloading === 'excel' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <FileSpreadsheet className="w-4 h-4" />
                )}
                <span>Download Excel</span>
            </button>

            <button
                onClick={() => handleDownload('both')}
                disabled={disabled || downloading !== null}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-lg transition-colors shadow-md hover:shadow-lg"
            >
                {downloading === 'both' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                    <Archive className="w-4 h-4" />
                )}
                <span>Download Both (ZIP)</span>
            </button>
        </div>
    );
}

