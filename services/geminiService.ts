
import type { HistoricalObject } from "../types";
import type { HistoricalEvent, HistoricalEventImageStatus } from "../types";

// URL backend FastAPI. Можно переопределить через Vite переменную окружения.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const analyzeImageForHistoricalObjects = async (
  file: File
): Promise<HistoricalObject[]> => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_URL}/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    // Пробуем показать деталь из backend, чтобы пользователю было понятнее.
    try {
      const errJson = await response.json();
      throw new Error(errJson.detail || "Не удалось выполнить анализ");
    } catch (parseErr) {
      throw new Error(`Ошибка анализа: ${response.statusText}`);
    }
  }

  const data = (await response.json()) as { objects?: HistoricalObject[] };
  return data.objects ?? [];
};

export const requestEventImage = async (
  event: HistoricalEvent
): Promise<{ taskId: string }> => {
  const response = await fetch(`${API_URL}/generate-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    throw new Error(errJson.detail || "Не удалось создать задачу генерации");
  }
  return (await response.json()) as { taskId: string };
};

export const fetchImageStatus = async (
  taskId: string
): Promise<HistoricalEventImageStatus> => {
  const response = await fetch(`${API_URL}/generation-status?taskId=${encodeURIComponent(taskId)}`);
  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    throw new Error(errJson.detail || "Не удалось получить статус задачи");
  }
  return (await response.json()) as HistoricalEventImageStatus;
};
