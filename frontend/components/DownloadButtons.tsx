"use client";

import React, { useState } from 'react';
import { FileText, FileSpreadsheet, Archive, Loader2 } from 'lucide-react';
import axios from 'axios';
import { Button } from '@/components/ui/button';

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
      const endpoint = `${apiUrl}/api/v1/quotations/${quotationId}/download?format=${format}`;
      const response = await axios.get(endpoint, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      const ext = format === 'both' ? 'zip' : format === 'pdf' ? 'pdf' : 'xlsx';
      link.setAttribute('download', `quotation_${quotationId}.${ext}`);
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

  const isLoading = downloading !== null;

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        onClick={() => handleDownload('pdf')}
        disabled={disabled || isLoading}
        className="gap-2 border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
      >
        {downloading === 'pdf' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <FileText className="h-3.5 w-3.5" />
        )}
        PDF
      </Button>

      <Button
        size="sm"
        variant="outline"
        onClick={() => handleDownload('excel')}
        disabled={disabled || isLoading}
        className="gap-2 border-green-200 text-green-700 hover:bg-green-50 hover:text-green-800 dark:border-green-800 dark:text-green-400 dark:hover:bg-green-950"
      >
        {downloading === 'excel' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <FileSpreadsheet className="h-3.5 w-3.5" />
        )}
        Excel
      </Button>

      <Button
        size="sm"
        onClick={() => handleDownload('both')}
        disabled={disabled || isLoading}
        className="gap-2"
      >
        {downloading === 'both' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Archive className="h-3.5 w-3.5" />
        )}
        Download All
      </Button>
    </div>
  );
}
