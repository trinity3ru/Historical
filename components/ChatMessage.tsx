
import React from 'react';
import type { Message } from '../types';

interface ChatMessageProps {
  message: Message;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.author === 'user';

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
        </div>
      </div>
    );
  }

  return null;
};

export default ChatMessage;
