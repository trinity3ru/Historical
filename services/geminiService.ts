
import { GoogleGenAI, Type } from "@google/genai";
import type { HistoricalObject } from '../types';
import { fileToBase64 } from "../utils/fileUtils";

const API_KEY = process.env.API_KEY;

if (!API_KEY) {
  throw new Error("API_KEY environment variable not set");
}

const ai = new GoogleGenAI({ apiKey: API_KEY });

const historicalObjectSchema = {
  type: Type.ARRAY,
  items: {
    type: Type.OBJECT,
    properties: {
      objectName: {
        type: Type.STRING,
        description: "Name of the historical object identified.",
      },
      confidence: {
        type: Type.NUMBER,
        description: "Confidence level of the identification, from 0.0 to 1.0.",
      },
      description: {
        type: Type.STRING,
        description: "A brief historical description of the object.",
      },
    },
    required: ["objectName", "confidence", "description"],
  },
};

export const analyzeImageForHistoricalObjects = async (file: File): Promise<HistoricalObject[]> => {
  try {
    const base64Image = await fileToBase64(file);
    const mimeType = file.type;

    const imagePart = {
      inlineData: {
        data: base64Image,
        mimeType: mimeType,
      },
    };

    const textPart = {
      text: `Analyze the image to identify historical objects. For each historical object found, provide its name, your confidence level (as a number between 0 and 1), and a brief description. If no such objects are found, return an empty array.`,
    };

    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: { parts: [imagePart, textPart] },
      config: {
        responseMimeType: "application/json",
        responseSchema: historicalObjectSchema,
      }
    });

    const jsonString = response.text.trim();
    if (!jsonString) {
        return [];
    }
    
    const parsedResponse = JSON.parse(jsonString);
    return parsedResponse as HistoricalObject[];

  } catch (error) {
    console.error("Error calling Gemini API:", error);
    throw new Error("Failed to analyze image with Gemini API.");
  }
};
