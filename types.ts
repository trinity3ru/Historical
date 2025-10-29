
export interface HistoricalObject {
  objectName: string;
  confidence: number;
  description: string;
}

export type MessageAuthor = 'user' | 'ai';

export interface Message {
  id: string;
  author: MessageAuthor;
  imageUrl?: string;
  text?: string;
}
