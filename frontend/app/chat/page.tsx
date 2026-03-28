import ChatInterface from '@/components/ChatInterface';
import { HardHat } from 'lucide-react';

export default function ChatPage() {
  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-60 shrink-0 border-r border-border bg-[hsl(220,18%,8%)] px-4 py-6 gap-6">
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-1">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
            <HardHat className="h-4 w-4 text-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-bold text-foreground leading-none">BuildAI</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Construction Quotation Agent</p>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px bg-border" />

        {/* Info cards */}
        <div className="space-y-3 text-xs text-muted-foreground">
          <div className="rounded-lg bg-muted p-3 space-y-1.5" dir="rtl">
            <p className="font-semibold text-foreground text-[11px] uppercase tracking-wide">ازاي بيشتغل؟</p>
            <p>قولنا تفاصيل مشروعك وهنحسبلك التكلفة والمواد والعمالة.</p>
          </div>

          <div className="rounded-lg bg-primary/5 border border-primary/10 p-3 space-y-1.5" dir="rtl">
            <p className="font-semibold text-primary text-[11px] uppercase tracking-wide">بنشتغل في</p>
            <ul className="space-y-1">
              <li>· شقق ومباني سكنية</li>
              <li>· تجديدات وتشطيبات</li>
              <li>· مشاريع تجارية</li>
              <li>· كل ده بالعربي</li>
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-auto text-[10px] text-muted-foreground px-1" dir="rtl">
          <p>أسعار السوق المصري</p>
          <p className="mt-0.5">الأسعار بالجنيه المصري</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col items-center justify-center p-4 md:p-6 overflow-hidden">
        <div className="w-full max-w-5xl flex flex-col gap-4 h-full">
          {/* Mobile header */}
          <div className="flex md:hidden items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
              <HardHat className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="font-bold text-foreground">BuildAI</span>
          </div>

          <ChatInterface />
        </div>
      </main>
    </div>
  );
}
