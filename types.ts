
export interface HistoricalObject {
  objectName: string;
  confidence: number;
  description: string;
  description_ru: string;
  events?: HistoricalEvent[];
}

export type MessageAuthor = 'user' | 'ai';

export interface Message {
  id: string;
  author: MessageAuthor;
  imageUrl?: string;
  text?: string;
}

export interface HistoricalEvent {
  title: string;
  title_ru: string;
  date: string;
  description: string;
  description_ru: string;
}
