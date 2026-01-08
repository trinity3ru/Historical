
import React, { useState, useRef } from 'react';
import Spinner from './Spinner';
import PaperAirplaneIcon from './icons/PaperAirplaneIcon';
import UploadIcon from './icons/UploadIcon';

interface ImageUploaderProps {
  onAnalyze: (file: File) => void;
  isLoading: boolean;
}

const ImageUploader: React.FC<ImageUploaderProps> = ({ onAnalyze, isLoading }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    }
  };

  const handleTriggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handleSubmit = () => {
    if (selectedFile) {
      onAnalyze(selectedFile);
      setSelectedFile(null);
      setPreviewUrl(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="bg-slate-800 rounded-lg p-3 flex items-center gap-3 transition-all duration-300 focus-within:ring-2 focus-within:ring-blue-500">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        accept="image/png, image/jpeg, image/webp"
      />
      <button
        onClick={handleTriggerUpload}
        disabled={isLoading}
        className="p-2 rounded-full bg-slate-700 hover:bg-slate-600 disabled:opacity-50 transition-colors"
        aria-label="Upload image"
      >
        <UploadIcon />
      </button>

      {previewUrl && (
        <div className="w-12 h-12 rounded-md overflow-hidden flex-shrink-0">
          <img src={previewUrl} alt="Preview" className="w-full h-full object-cover" />
        </div>
      )}
      
      <div className="flex-1 text-slate-400">
        {selectedFile ? selectedFile.name : "Select an image to analyze..."}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!selectedFile || isLoading}
        className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-bold p-3 rounded-full transition-all duration-200 flex items-center justify-center w-12 h-12 flex-shrink-0"
        aria-label="Analyze image"
      >
        {isLoading ? <Spinner /> : <PaperAirplaneIcon />}
      </button>
    </div>
  );
};

export default ImageUploader;
