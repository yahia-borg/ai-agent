import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Construction Agent',
  description: 'AI-powered construction quotation generation system',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}

