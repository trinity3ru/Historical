
import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { Message } from './types';
import { analyzeImageForHistoricalObjects } from './services/geminiService';
import ImageUploader from './components/ImageUploader';
import ChatMessage from './components/ChatMessage';
import WelcomeMessage from './components/WelcomeMessage';

const App: React.FC = () => {
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  const handleAnalyze = useCallback(async (file: File) => {
    setIsLoading(true);
    setError(null);

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      author: 'user',
      imageUrl: URL.createObjectURL(file),
    };
    setChatHistory(prev => [...prev, userMessage]);

    try {
      const results = await analyzeImageForHistoricalObjects(file);
      
      let aiResponseText = '';
      let aiEvents: any = undefined;
      if (results.length > 0) {
        const confidentResults = results.filter(obj => obj.confidence >= 0.9);
        const used = confidentResults.length > 0 ? confidentResults : results;
        aiResponseText = used.map(obj => {
          const header = `**${obj.objectName}** (Уверенность: ${Math.round(obj.confidence * 100)}%)`;
          const desc = `RU: ${obj.description_ru}\nEN: ${obj.description}`;
          const eventsBlock = (obj.events && obj.events.length > 0)
            ? obj.events.map(ev =>
                `- ${ev.date}: ${ev.title_ru} / ${ev.title}\n  RU: ${ev.description_ru}\n  EN: ${ev.description}`
              ).join('\n')
            : 'События: нет данных';
          return `${header}\n${desc}\n${eventsBlock}`;
        }).join('\n\n');

        // Сохраняем события для генерации изображений (первый объект).
        const firstWithEvents = used.find(obj => obj.events && obj.events.length > 0);
        if (firstWithEvents?.events) {
          aiEvents = firstWithEvents.events;
        }
      } else {
        aiResponseText = "Не удалось распознать исторические объекты. Попробуйте другое фото.";
      }

      const aiMessage: Message = {
        id: `ai-${Date.now()}`,
        author: 'ai',
        text: aiResponseText,
        // @ts-expect-error доп. поле для событий (используется в ChatMessage)
        events: aiEvents,
      };
      setChatHistory(prev => [...prev, aiMessage]);

    } catch (err) {
      console.error(err);
      const errorMessage = "Sorry, I encountered an error trying to analyze the image. Please check your API key or try again later.";
      setError(errorMessage);
       const aiErrorMessage: Message = {
        id: `ai-error-${Date.now()}`,
        author: 'ai',
        text: errorMessage,
      };
      setChatHistory(prev => [...prev, aiErrorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <div className="flex flex-col h-screen bg-slate-900 font-sans">
      <header className="bg-slate-800/50 backdrop-blur-sm shadow-md p-4 border-b border-slate-700">
        <h1 className="text-xl md:text-2xl font-bold text-center text-transparent bg-clip-text bg-gradient-to-r from-teal-300 to-blue-500">
          Historical Object Finder
        </h1>
      </header>
      
      <main ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {chatHistory.length === 0 && <WelcomeMessage />}
        {chatHistory.map(msg => <ChatMessage key={msg.id} message={msg} />)}
        {error && <div className="text-red-400 text-center p-2">{error}</div>}
      </main>

      <footer className="p-4 bg-slate-900 border-t border-slate-700">
        <div className="max-w-3xl mx-auto">
          <ImageUploader onAnalyze={handleAnalyze} isLoading={isLoading} />
        </div>
      </footer>
    </div>
  );
};

export default App;
