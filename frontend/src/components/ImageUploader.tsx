import { useState, useRef } from "react";
import { X, Image as ImageIcon, Sparkles, Plus } from "lucide-react";
import { cn } from "../lib/utils";

interface ImageUploaderProps {
  onImageSelect: (imageData: string, format: string) => void;
  disabled?: boolean;
}

export function ImageUploader({ onImageSelect, disabled }: ImageUploaderProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
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
          {/* 图片预览容器 - 添加高级阴影和边框效果 */}
          <div className={cn(
            "relative overflow-hidden rounded-xl shadow-lg",
            "border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent",
            "transition-all duration-300",
            isHovered && "border-primary/50 shadow-primary/20"
          )}>
            <img
              src={preview}
              alt="Preview"
              className="h-14 w-14 object-cover transition-transform duration-300 group-hover:scale-105"
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
            />
            {/* 渐变遮罩 - 更精致的光影效果 */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent pointer-events-none" />
            {/* 顶部光泽效果 */}
            <div className="absolute top-0 left-0 right-0 h-1/3 bg-gradient-to-b from-white/20 to-transparent pointer-events-none" />

            {/* 删除按钮 - 更精致的设计 */}
            <button
              type="button"
              onClick={handleRemove}
              disabled={disabled}
              className={cn(
                "absolute top-1.5 right-1.5 h-6 w-6 rounded-xl",
                "bg-background/95 backdrop-blur-md",
                "border border-border/50 shadow-lg",
                "flex items-center justify-center",
                "transition-all duration-300",
                "opacity-0 translate-y-1 group-hover:opacity-100 group-hover:translate-y-0",
                "hover:bg-destructive hover:text-destructive-foreground hover:border-destructive hover:scale-110",
                disabled && "opacity-50 cursor-not-allowed"
              )}
            >
              <X className="w-3.5 h-3.5" />
            </button>

            {/* 图片指示器 - 左下角小图标 */}
            <div className="absolute bottom-1.5 left-1.5 h-5 w-5 rounded-lg bg-background/80 backdrop-blur-sm border border-border/30 flex items-center justify-center">
              <ImageIcon className="w-3 h-3 text-muted-foreground" />
            </div>
          </div>
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
            "group relative",
            "h-12 w-12 rounded-2xl",
            "flex items-center justify-center",
            "overflow-hidden",
            "transition-all duration-300 ease-out",
            // 基础状态
            "bg-gradient-to-br from-muted via-muted to-muted/80",
            "border-2 border-input shadow-md",
            // 悬停状态
            "hover:shadow-lg hover:shadow-primary/10 hover:scale-105",
            "hover:border-primary/40 hover:from-primary/20 hover:via-primary/10 hover:to-primary/5",
            // 拖拽状态
            isDragging && "border-primary bg-primary/10 shadow-xl shadow-primary/30 scale-110 ring-4 ring-primary/30",
            // 禁用状态
            disabled && "opacity-40 cursor-not-allowed hover:scale-100 hover:shadow-md hover:border-input hover:bg-muted"
          )}
          title="添加图片"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          {/* 背景网格装饰 */}
          <div className="absolute inset-0 opacity-10">
            <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(255,255,255,.1)_50%,transparent_75%)] bg-[length:4px]" />
          </div>

          {/* 图标容器 */}
          <div className="relative z-10">
            <ImageIcon className={cn(
              "w-6 h-6 transition-all duration-300",
              "text-muted-foreground",
              isDragging || isHovered ? "scale-110 text-primary" : ""
            )} />
            {/* 闪光装饰图标 */}
            <Sparkles className={cn(
              "absolute -top-1 -right-1 w-3 h-3 text-primary",
              "transition-all duration-300",
              isDragging ? "scale-125 rotate-12 opacity-100" : "opacity-60",
              isHovered && !isDragging && "scale-110 opacity-80 rotate-0"
            )} />
          </div>

          {/* 拖拽时的脉冲动画 */}
          {isDragging && (
            <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-pulse" />
          )}
        </button>
      )}
    </div>
  );
}
