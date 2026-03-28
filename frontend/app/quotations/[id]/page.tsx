'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import axios from 'axios'
import { ArrowLeft, CheckCircle2, XCircle, Clock, Loader2, HardHat } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import DownloadButtons from '@/components/DownloadButtons'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

function getStatusVariant(status: string): 'default' | 'success' | 'destructive' | 'warning' | 'info' {
  switch (status) {
    case 'completed': return 'success'
    case 'failed': return 'destructive'
    case 'processing':
    case 'data_collection':
    case 'cost_calculation': return 'info'
    default: return 'warning'
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case 'pending': return 'Pending'
    case 'processing': return 'Processing'
    case 'data_collection': return 'Collecting Data'
    case 'cost_calculation': return 'Calculating Costs'
    case 'completed': return 'Completed'
    case 'failed': return 'Failed'
    default: return status
  }
}

function getProgressValue(status: string) {
  switch (status) {
    case 'pending': return 5
    case 'data_collection': return 40
    case 'cost_calculation': return 75
    case 'completed': return 100
    case 'failed': return 100
    default: return 10
  }
}

interface CostRow {
  label: string;
  labelAr: string;
  value: number | undefined;
  percentage?: number;
  isTotal?: boolean;
}

export default function QuotationStatusPage() {
  const params = useParams()
  const router = useRouter()
  const quotationId = params.id as string

  const [quotation, setQuotation] = useState<any>(null)
  const [status, setStatus] = useState<any>(null)
  const [quotationData, setQuotationData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchQuotation()
    fetchStatus()
    fetchQuotationData()

    const interval = setInterval(() => {
      if (status?.status !== 'completed' && status?.status !== 'failed') {
        fetchStatus()
        fetchQuotationData()
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [quotationId, status?.status])

  const fetchQuotation = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}`)
      setQuotation(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load quotation')
      setLoading(false)
    }
  }

  const fetchStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}/status`)
      setStatus(res.data)
      setLoading(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load status')
      setLoading(false)
    }
  }

  const fetchQuotationData = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}?include_data=true`)
      if (res.data.quotation_data) setQuotationData(res.data.quotation_data)
    } catch {
      // silently fail
    }
  }

  if (loading && !quotation) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm">Loading quotation…</p>
        </div>
      </div>
    )
  }

  if (error && !quotation) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background p-4">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-2 text-destructive">
              <XCircle className="h-5 w-5" />
              <p className="text-sm font-medium">{error}</p>
            </div>
            <Button variant="outline" onClick={() => router.push('/')} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const cb = quotationData?.cost_breakdown
  const currency = cb?.currency || 'EGP'
  const fmt = (n?: number) => n ? `${currency} ${n.toLocaleString()}` : '—'

  const costRows: CostRow[] = cb ? [
    { label: 'Materials', labelAr: 'المواد', value: cb.materials?.subtotal, percentage: cb.materials?.percentage },
    { label: 'Labor', labelAr: 'العمالة', value: cb.labor?.subtotal, percentage: cb.labor?.percentage },
    { label: 'Permits & Fees', labelAr: 'التصاريح والرسوم', value: cb.permits_and_fees?.subtotal },
    { label: `Contingency (${cb.contingency?.percentage ?? 0}%)`, labelAr: 'الطوارئ', value: cb.contingency?.subtotal },
    { label: `Markup (${cb.markup?.percentage ?? 0}%)`, labelAr: 'هامش الربح', value: cb.markup?.subtotal },
  ].filter(r => r.value !== undefined) : []

  return (
    <div className="min-h-screen bg-background">
      {/* Top nav */}
      <header className="border-b border-border bg-card px-6 py-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0">
          <HardHat className="h-3.5 w-3.5 text-primary-foreground" />
        </div>
        <span className="font-bold text-sm text-foreground">BuildAI</span>
        <Separator orientation="vertical" className="h-4 mx-1" />
        <span className="text-sm text-muted-foreground">Quotation Details</span>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <Button variant="ghost" size="sm" onClick={() => router.push('/')} className="gap-2 -ml-1">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>

        {/* Project details */}
        {quotation && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Project Details</CardTitle>
              <CardDescription className="font-mono text-xs">{quotationId}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-foreground">{quotation.project_description}</p>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground mt-2">
                {quotation.location && <span>📍 {quotation.location}</span>}
                {quotation.project_type && (
                  <span>🏗 {quotation.project_type.replace('_', ' ')}</span>
                )}
                {quotation.timeline && <span>⏱ {quotation.timeline}</span>}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Status */}
        {status && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Status</CardTitle>
                <Badge variant={getStatusVariant(status.status)}>
                  {getStatusLabel(status.status)}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{status.current_stage ? `Stage: ${status.current_stage}` : 'Progress'}</span>
                  <span>{status.progress ?? getProgressValue(status.status)}%</span>
                </div>
                <Progress
                  value={status.progress ?? getProgressValue(status.status)}
                  className={status.status === 'failed' ? '[&>div]:bg-destructive' : ''}
                />
              </div>

              {status.estimated_completion && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  Est. completion: {new Date(status.estimated_completion).toLocaleString()}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Updated: {new Date(status.last_update).toLocaleString()}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Cost breakdown */}
        {cb && costRows.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                Cost Breakdown <span className="text-muted-foreground font-normal text-sm">/ تفاصيل التكلفة</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground border-b border-border">
                    <th className="text-start pb-2 font-medium">Category</th>
                    <th className="text-start pb-2 font-medium hidden sm:table-cell">الفئة</th>
                    <th className="text-end pb-2 font-medium">Amount</th>
                    <th className="text-end pb-2 font-medium hidden sm:table-cell">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {costRows.map((row, i) => (
                    <tr key={i} className="py-2">
                      <td className="py-2.5 text-foreground">{row.label}</td>
                      <td className="py-2.5 text-muted-foreground hidden sm:table-cell" dir="rtl">{row.labelAr}</td>
                      <td className="py-2.5 text-end font-mono text-foreground">{fmt(row.value)}</td>
                      <td className="py-2.5 text-end text-muted-foreground hidden sm:table-cell">
                        {row.percentage !== undefined ? `${row.percentage}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
                {quotationData.total_cost && (
                  <tfoot>
                    <tr className="border-t-2 border-primary/30">
                      <td colSpan={2} className="pt-3 font-semibold text-foreground">
                        Total Estimated Cost <span className="text-muted-foreground font-normal" dir="rtl">/ التكلفة الإجمالية</span>
                      </td>
                      <td className="pt-3 text-end font-bold text-primary font-mono text-base">
                        {fmt(quotationData.total_cost)}
                      </td>
                      <td className="hidden sm:table-cell" />
                    </tr>
                  </tfoot>
                )}
              </table>
            </CardContent>
          </Card>
        )}

        {/* Completed — download */}
        {status?.status === 'completed' && (
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="pt-5 pb-5">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                  <span className="text-sm font-medium text-foreground">Quotation complete — download your report</span>
                </div>
                <DownloadButtons quotationId={quotationId} />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Failed */}
        {status?.status === 'failed' && (
          <Card className="border-destructive/20 bg-destructive/5">
            <CardContent className="pt-5 pb-5 flex items-center gap-2">
              <XCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive font-medium">
                Processing failed. Please start a new chat to try again.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
