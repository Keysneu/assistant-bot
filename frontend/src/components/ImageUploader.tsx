import { useState, useRef } from "react";
import { X, Image as ImageIcon } from "lucide-react";
import { cn } from "../lib/utils";

interface ImageUploaderProps {
  onImageSelect: (imageData: string, format: string) => void;
  disabled?: boolean;
}

export function ImageUploader({ onImageSelect, disabled }: ImageUploaderProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (file: File | null) => {
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      alert("请选择图片文件");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      alert("图片大小不能超过 10MB");
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      if (result) {
        const formatMatch = result.match(/data:image\/([a-zA-Z+]+);base64/);
        const format = formatMatch ? formatMatch[1] : "png";
        const base64Data = result.split(",")[1];

        setPreview(result);
        onImageSelect(base64Data, format);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    handleFileSelect(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFileSelect(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleRemove = () => {
    setPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    onImageSelect("", "");
  };

  return (
    <div className="relative">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleInputChange}
        className="hidden"
        disabled={disabled}
      />

      {preview ? (
        <div className="relative group">
          <img
            src={preview}
            alt="Preview"
            className="h-20 w-20 object-cover rounded-lg border border-border"
          />
          <button
            type="button"
            onClick={handleRemove}
            disabled={disabled}
            className={cn(
              "absolute -top-2 -right-2 h-6 w-6 rounded-full bg-destructive text-destructive-foreground",
              "flex items-center justify-center opacity-0 group-hover:opacity-100",
              "transition-opacity duration-200",
              disabled && "opacity-50 cursor-not-allowed"
            )}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={cn(
            "h-10 px-3 rounded-lg border border-dashed transition-all duration-200",
            "flex items-center gap-2 text-sm font-medium",
            "hover:border-primary/50 hover:bg-accent/5",
            isDragging && "border-primary bg-accent/10",
            disabled && "opacity-50 cursor-not-allowed hover:border-input hover:bg-transparent"
          )}
        >
          <ImageIcon className="w-4 h-4" />
          <span>
            {isDragging ? "松开上传图片" : "添加图片"}
          </span>
        </button>
      )}
    </div>
  );
}
