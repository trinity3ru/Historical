
import React, { useState } from 'react';
import type { Message, HistoricalEvent } from '../types';
import { requestEventImage, fetchImageStatus } from '../services/geminiService';

interface ChatMessageProps {
  message: Message;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.author === 'user';
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [genImageUrl, setGenImageUrl] = useState<string | null>(null);

  if (isUser && message.imageUrl) {
    return (
      <div className="flex justify-end">
        <div className="max-w-xs md:max-w-sm lg:max-w-md bg-blue-600 rounded-lg p-2">
          <img src={message.imageUrl} alt="User upload" className="rounded-md object-contain" />
        </div>
      </div>
    );
  }

  if (!isUser && message.text) {
    const lines = message.text.split('\n');
    const events = (message as any).events as HistoricalEvent[] | undefined;

    const handleGenerate = async (event: HistoricalEvent) => {
      setGenError(null);
      setIsGenerating(true);
      setGenImageUrl(null);
      try {
        const { taskId } = await requestEventImage(event);
        let attempts = 0;
        const maxAttempts = 12; // ~24 сек при шаге 2с
        const wait = (ms: number) => new Promise(res => setTimeout(res, ms));
        while (attempts < maxAttempts) {
          const status = await fetchImageStatus(taskId);
          if (status.state === 'success' && status.resultUrls && status.resultUrls.length > 0) {
            setGenImageUrl(status.resultUrls[0]);
            setIsGenerating(false);
            return;
          }
          if (status.state === 'fail') {
            throw new Error(status.failMsg || 'Генерация не удалась');
          }
          attempts += 1;
          await wait(2000);
        }
        throw new Error('Таймаут ожидания генерации');
      } catch (err: any) {
        setGenError(err?.message || 'Ошибка генерации изображения');
        setIsGenerating(false);
      }
    };

    return (
      <div className="flex justify-start">
        <div className="max-w-xl bg-slate-700 rounded-lg p-4 space-y-3">
          <div className="text-slate-200 whitespace-pre-wrap leading-relaxed">
            {lines.map((line, idx) => (
              <p key={idx} className="mb-1 last:mb-0">
                {line}
              </p>
            ))}
          </div>

          {events && events.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm text-slate-300">События:</div>
              {events.map((ev, idx) => (
                <div key={idx} className="border border-slate-600 rounded p-2 space-y-1">
                  <div className="text-slate-100 font-semibold">{ev.title_ru} ({ev.date})</div>
                  <div className="text-slate-200 text-sm">RU: {ev.description_ru}</div>
                  <div className="text-slate-400 text-xs">EN: {ev.description}</div>
                  <button
                    onClick={() => handleGenerate(ev)}
                    disabled={isGenerating}
                    className="mt-1 px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white text-sm"
                  >
                    {isGenerating ? 'Генерация...' : 'Сгенерировать изображение'}
                  </button>
                </div>
              ))}
            </div>
          )}

          {genError && <div className="text-red-400 text-sm">{genError}</div>}
          {genImageUrl && (
            <div className="mt-2">
              <div className="text-sm text-slate-300 mb-1">Результат генерации:</div>
              <img src={genImageUrl} alt="Generated" className="rounded border border-slate-600" />
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
};

export default ChatMessage;
