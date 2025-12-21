import ChatInterface from '@/components/ChatInterface';

export default function ChatPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 md:p-12 bg-slate-50 dark:bg-slate-950">
      <div className="z-10 w-full max-w-5xl items-center justify-between text-sm flex flex-col gap-8">
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 pb-2">
            Construction AI Agent
          </h1>
          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Your intelligent assistant for cost estimation.
          </p>
        </div>

        <ChatInterface />
      </div>
    </main>
  );
}

