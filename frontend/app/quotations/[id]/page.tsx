'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import axios from 'axios'
import DownloadButtons from '@/components/DownloadButtons'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

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

    // Poll for status updates every 3 seconds if not completed
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
      const response = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}`)
      setQuotation(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load quotation')
      setLoading(false)
    }
  }

  const fetchStatus = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}/status`)
      setStatus(response.data)
      setLoading(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load status')
      setLoading(false)
    }
  }

  const fetchQuotationData = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/v1/quotations/${quotationId}?include_data=true`)
      if (response.data.quotation_data) {
        setQuotationData(response.data.quotation_data)
      }
    } catch (err: any) {
      // Silently fail - quotation data might not be available yet
    }
  }


  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return '#2e7d32'
      case 'failed':
        return '#d32f2f'
      case 'processing':
      case 'data_collection':
      case 'cost_calculation':
        return '#0070f3'
      default:
        return '#666'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'pending':
        return 'Pending'
      case 'processing':
        return 'Processing'
      case 'data_collection':
        return 'Collecting Data'
      case 'cost_calculation':
        return 'Calculating Costs'
      case 'completed':
        return 'Completed'
      case 'failed':
        return 'Failed'
      default:
        return status
    }
  }

  if (loading && !quotation) {
    return (
      <div className="container">
        <div className="card">
          <div style={{ textAlign: 'center' }}>
            <span className="loading" style={{ width: '40px', height: '40px', borderWidth: '4px' }}></span>
            <p style={{ marginTop: '1rem' }}>Loading quotation...</p>
          </div>
        </div>
      </div>
    )
  }

  if (error && !quotation) {
    return (
      <div className="container">
        <div className="card">
          <div className="error">{error}</div>
          <button
            className="btn btn-primary"
            onClick={() => router.push('/')}
            style={{ marginTop: '1rem' }}
          >
            Back to Home
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="card">
        <button
          onClick={() => router.push('/')}
          style={{
            marginBottom: '2rem',
            background: 'none',
            border: 'none',
            color: '#0070f3',
            cursor: 'pointer',
            textDecoration: 'underline'
          }}
        >
          ← Back to Home
        </button>

        <h1 style={{ marginBottom: '1rem' }}>Quotation Status</h1>
        <p style={{ marginBottom: '2rem', color: '#666' }}>
          Quotation ID: <strong>{quotationId}</strong>
        </p>

        {quotation && (
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ marginBottom: '1rem', fontSize: '1.25rem' }}>Project Details</h2>
            <div style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px' }}>
              <p><strong>Description:</strong> {quotation.project_description}</p>
              {quotation.location && <p><strong>Location:</strong> {quotation.location}</p>}
              {quotation.zip_code && <p><strong>Zip Code:</strong> {quotation.zip_code}</p>}
              {quotation.project_type && (
                <p><strong>Project Type:</strong> {quotation.project_type.replace('_', ' ')}</p>
              )}
              {quotation.timeline && <p><strong>Timeline:</strong> {quotation.timeline}</p>}
            </div>
          </div>
        )}

        {status && (
          <div>
            <h2 style={{ marginBottom: '1rem', fontSize: '1.25rem' }}>Status</h2>
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                <span
                  style={{
                    padding: '0.5rem 1rem',
                    borderRadius: '4px',
                    backgroundColor: getStatusColor(status.status),
                    color: 'white',
                    fontWeight: '600'
                  }}
                >
                  {getStatusLabel(status.status)}
                </span>
                {status.current_stage && (
                  <span style={{ color: '#666' }}>Stage: {status.current_stage}</span>
                )}
              </div>

              {status.progress !== null && (
                <div style={{ marginTop: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>Progress</span>
                    <span>{status.progress}%</span>
                  </div>
                  <div
                    style={{
                      width: '100%',
                      height: '24px',
                      backgroundColor: '#e0e0e0',
                      borderRadius: '4px',
                      overflow: 'hidden'
                    }}
                  >
                    <div
                      style={{
                        width: `${status.progress}%`,
                        height: '100%',
                        backgroundColor: getStatusColor(status.status),
                        transition: 'width 0.3s ease'
                      }}
                    />
                  </div>
                </div>
              )}

              {status.estimated_completion && (
                <p style={{ marginTop: '1rem', color: '#666', fontSize: '0.875rem' }}>
                  Estimated completion: {new Date(status.estimated_completion).toLocaleString()}
                </p>
              )}

              <p style={{ marginTop: '1rem', color: '#666', fontSize: '0.875rem' }}>
                Last updated: {new Date(status.last_update).toLocaleString()}
              </p>
            </div>
          </div>
        )}

        {quotationData && quotationData.cost_breakdown && (
          <div style={{ marginTop: '2rem' }}>
            <h2 style={{ marginBottom: '1rem', fontSize: '1.25rem' }}>Cost Breakdown / تفاصيل التكلفة</h2>
            <div style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px' }}>
              {(() => {
                const currency = quotationData.cost_breakdown.currency || 'EGP'
                const currencySymbol = currency === 'EGP' ? 'EGP' : '$'
                return (
                  <>
                    {quotationData.cost_breakdown.materials && (
                      <div style={{ marginBottom: '1rem' }}>
                        <p><strong>Materials / المواد:</strong> {currencySymbol} {quotationData.cost_breakdown.materials.subtotal?.toLocaleString()} 
                          ({quotationData.cost_breakdown.materials.percentage}%)</p>
                      </div>
                    )}
                    {quotationData.cost_breakdown.labor && (
                      <div style={{ marginBottom: '1rem' }}>
                        <p><strong>Labor / العمالة:</strong> {currencySymbol} {quotationData.cost_breakdown.labor.subtotal?.toLocaleString()} 
                          ({quotationData.cost_breakdown.labor.percentage}%)</p>
                      </div>
                    )}
                    {quotationData.cost_breakdown.permits_and_fees && (
                      <div style={{ marginBottom: '1rem' }}>
                        <p><strong>Permits & Fees / التصاريح والرسوم:</strong> {currencySymbol} {quotationData.cost_breakdown.permits_and_fees.subtotal?.toLocaleString()}</p>
                      </div>
                    )}
                    {quotationData.cost_breakdown.contingency && (
                      <div style={{ marginBottom: '1rem' }}>
                        <p><strong>Contingency ({quotationData.cost_breakdown.contingency.percentage}%) / الطوارئ:</strong> 
                          {currencySymbol} {quotationData.cost_breakdown.contingency.subtotal?.toLocaleString()}</p>
                      </div>
                    )}
                    {quotationData.cost_breakdown.markup && (
                      <div style={{ marginBottom: '1rem' }}>
                        <p><strong>Markup ({quotationData.cost_breakdown.markup.percentage}%) / هامش الربح:</strong> 
                          {currencySymbol} {quotationData.cost_breakdown.markup.subtotal?.toLocaleString()}</p>
                      </div>
                    )}
                    {quotationData.total_cost && (
                      <div style={{ 
                        marginTop: '1.5rem', 
                        paddingTop: '1rem', 
                        borderTop: '2px solid #0070f3',
                        fontSize: '1.25rem',
                        fontWeight: 'bold'
                      }}>
                        <p><strong>Total Estimated Cost / التكلفة الإجمالية المقدرة: {currencySymbol} {quotationData.total_cost.toLocaleString()}</strong></p>
                      </div>
                    )}
                  </>
                )
              })()}
            </div>
          </div>
        )}

        {status?.status === 'completed' && (
          <div style={{ marginTop: '2rem' }}>
            <div style={{ padding: '1rem', background: '#e8f5e9', borderRadius: '4px', marginBottom: '1rem' }}>
              <p className="success" style={{ marginBottom: '1rem' }}>
                ✓ Quotation processing completed!
              </p>
              <div style={{ marginTop: '1rem' }}>
                <DownloadButtons quotationId={quotationId} />
              </div>
            </div>
          </div>
        )}

        {status?.status === 'failed' && (
          <div style={{ marginTop: '2rem', padding: '1rem', background: '#ffebee', borderRadius: '4px' }}>
            <p className="error">
              ✗ Quotation processing failed. Please try creating a new quotation.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

