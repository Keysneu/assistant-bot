import { useState, useRef, useEffect } from "react";
import { X, Image as ImageIcon, Sparkles, Plus } from "lucide-react";
import { cn } from "../lib/utils";

export interface SelectedImagePayload {
  file: File;
  previewDataUrl: string;
  format: string;
}

interface ImageUploaderProps {
  value?: SelectedImagePayload[];
  onImagesChange: (payloads: SelectedImagePayload[]) => void;
  disabled?: boolean;
  disabledReason?: string;
  maxImages?: number;
}

export function ImageUploader({
  value,
  onImagesChange,
  disabled,
  disabledReason,
  maxImages = 4,
}: ImageUploaderProps) {
  const [images, setImages] = useState<SelectedImagePayload[]>(value || []);
  const [isDragging, setIsDragging] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setImages(value || []);
  }, [value]);

  const MAX_EDGE = 4096;
  const TARGET_MIME = "image/jpeg";
  const TARGET_QUALITY = 0.95;
  const TARGET_MAX_BYTES = 8 * 1024 * 1024;

  const readFileAsDataURL = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result;
        if (typeof result === "string") {
          resolve(result);
        } else {
          reject(new Error("读取图片失败"));
        }
      };
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.readAsDataURL(file);
    });

  const loadImage = (src: string): Promise<HTMLImageElement> =>
    new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("图片解码失败"));
      img.src = src;
    });

  const canvasToBlob = (canvas: HTMLCanvasElement, quality: number): Promise<Blob> =>
    new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error("图片编码失败"));
            return;
          }
          resolve(blob);
        },
        TARGET_MIME,
        quality,
      );
    });

  const drawScaled = (img: HTMLImageElement, width: number, height: number): HTMLCanvasElement => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("浏览器不支持 Canvas");
    }
    ctx.drawImage(img, 0, 0, width, height);
    return canvas;
  };

  const encodeWithBudget = async (canvas: HTMLCanvasElement): Promise<Blob> => {
    const qualitySteps = [TARGET_QUALITY, 0.74, 0.66, 0.58];
    let working = canvas;
    let smallest: Blob | null = null;

    for (let resizeAttempt = 0; resizeAttempt < 4; resizeAttempt += 1) {
      for (const quality of qualitySteps) {
        const blob = await canvasToBlob(working, quality);
        if (!smallest || blob.size < smallest.size) {
          smallest = blob;
        }
        if (blob.size <= TARGET_MAX_BYTES) {
          return blob;
        }
      }

      const longestEdge = Math.max(working.width, working.height);
      if (longestEdge <= 640) {
        break;
      }

      const scaledWidth = Math.max(1, Math.round(working.width * 0.85));
      const scaledHeight = Math.max(1, Math.round(working.height * 0.85));
      const next = document.createElement("canvas");
      next.width = scaledWidth;
      next.height = scaledHeight;
      const ctx = next.getContext("2d");
      if (!ctx) {
        break;
      }
      ctx.drawImage(working, 0, 0, scaledWidth, scaledHeight);
      working = next;
    }

    if (!smallest) {
      throw new Error("图片编码失败");
    }
    return smallest;
  };

  const normalizeImage = async (file: File): Promise<SelectedImagePayload> => {
    const originalDataUrl = await readFileAsDataURL(file);
    const img = await loadImage(originalDataUrl);

    const maxSide = Math.max(img.width, img.height);
    const scale = maxSide > MAX_EDGE ? MAX_EDGE / maxSide : 1;
    const width = Math.max(1, Math.round(img.width * scale));
    const height = Math.max(1, Math.round(img.height * scale));

    const canvas = drawScaled(img, width, height);
    const blob = await encodeWithBudget(canvas);
    const compressedDataUrl = await readFileAsDataURL(
      new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: TARGET_MIME }),
    );

    return {
      file: new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: TARGET_MIME }),
      previewDataUrl: compressedDataUrl,
      format: "jpeg",
    };
  };

  const emitImages = (next: SelectedImagePayload[]) => {
    setImages(next);
    onImagesChange(next);
  };

  const processFiles = async (files: File[]) => {
    if (!files.length || disabled) {
      return;
    }

    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) {
      alert("请选择图片文件");
      return;
    }

    const remainingSlots = Math.max(0, maxImages - images.length);
    if (remainingSlots <= 0) {
      alert(`最多可上传 ${maxImages} 张图片`);
      return;
    }

    if (imageFiles.length > remainingSlots) {
      alert(`最多可上传 ${maxImages} 张图片，已自动截取前 ${remainingSlots} 张`);
    }

    const selected = imageFiles.slice(0, remainingSlots);
    const nextBatch: SelectedImagePayload[] = [];

    for (const file of selected) {
      if (file.size > 64 * 1024 * 1024) {
        alert(`图片 ${file.name} 超过 64MB，已跳过`);
        continue;
      }

      try {
        const payload = await normalizeImage(file);
        nextBatch.push(payload);
      } catch (error) {
        console.error("图片处理失败:", error);
        alert(`图片 ${file.name} 处理失败，已跳过`);
      }
    }

    if (!nextBatch.length) {
      return;
    }

    emitImages([...images, ...nextBatch]);
  };

  const handleInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    await processFiles(files);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    await processFiles(files);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleRemoveAt = (index: number) => {
    const next = images.filter((_, idx) => idx !== index);
    emitImages(next);
  };

  const handleClear = () => {
    emitImages([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const buttonTitle = disabled && disabledReason ? disabledReason : "添加图片";
  const canAddMore = images.length < maxImages;

  return (
    <div className="relative" onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        onChange={handleInputChange}
        className="hidden"
        disabled={disabled}
      />

      {images.length > 0 ? (
        <div className="flex items-center gap-2">
          {images.map((item, index) => (
            <div
              key={`${item.previewDataUrl}-${index}`}
              className={cn(
                "relative overflow-hidden rounded-xl shadow-lg border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent",
                isHovered && "border-primary/50 shadow-primary/20"
              )}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
            >
              <img
                src={item.previewDataUrl}
                alt={`Preview ${index + 1}`}
                className="h-14 w-14 object-cover transition-transform duration-300 hover:scale-105"
              />
              <button
                type="button"
                onClick={() => handleRemoveAt(index)}
                disabled={disabled}
                className={cn(
                  "absolute top-1.5 right-1.5 h-6 w-6 rounded-xl bg-background/95 backdrop-blur-md border border-border/50 shadow-lg flex items-center justify-center",
                  "hover:bg-destructive hover:text-destructive-foreground hover:border-destructive",
                  disabled && "opacity-50 cursor-not-allowed"
                )}
              >
                <X className="w-3.5 h-3.5" />
              </button>
              <div className="absolute bottom-1.5 left-1.5 h-5 min-w-5 px-1 rounded-lg bg-background/80 backdrop-blur-sm border border-border/30 flex items-center justify-center text-[10px] text-muted-foreground">
                {index + 1}
              </div>
            </div>
          ))}

          {canAddMore && (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className={cn(
                "h-12 w-12 rounded-2xl border-2 border-dashed border-input text-muted-foreground flex items-center justify-center",
                "hover:border-primary/50 hover:text-primary transition-all",
                disabled && "opacity-40 cursor-not-allowed"
              )}
              title={buttonTitle}
            >
              <Plus className="w-5 h-5" />
            </button>
          )}

          <button
            type="button"
            onClick={handleClear}
            disabled={disabled}
            className={cn(
              "h-12 w-8 rounded-xl border border-border text-muted-foreground flex items-center justify-center",
              "hover:text-foreground hover:border-primary/40 transition-all",
              disabled && "opacity-40 cursor-not-allowed"
            )}
            title="清空图片"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className={cn(
            "group relative",
            "h-12 w-12 rounded-2xl",
            "flex items-center justify-center",
            "overflow-hidden",
            "transition-all duration-300 ease-out",
            "bg-gradient-to-br from-muted via-muted to-muted/80",
            "border-2 border-input shadow-md",
            "hover:shadow-lg hover:shadow-primary/10 hover:scale-105",
            "hover:border-primary/40 hover:from-primary/20 hover:via-primary/10 hover:to-primary/5",
            isDragging && "border-primary bg-primary/10 shadow-xl shadow-primary/30 scale-110 ring-4 ring-primary/30",
            disabled && "opacity-40 cursor-not-allowed hover:scale-100 hover:shadow-md hover:border-input hover:bg-muted"
          )}
          title={buttonTitle}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          <div className="absolute inset-0 opacity-10">
            <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(255,255,255,.1)_50%,transparent_75%)] bg-[length:4px]" />
          </div>

          <div className="relative z-10">
            <ImageIcon className={cn(
              "w-6 h-6 transition-all duration-300",
              "text-muted-foreground",
              isDragging || isHovered ? "scale-110 text-primary" : ""
            )} />
            <Sparkles className={cn(
              "absolute -top-1 -right-1 w-3 h-3 text-primary",
              "transition-all duration-300",
              isDragging ? "scale-125 rotate-12 opacity-100" : "opacity-60",
              isHovered && !isDragging && "scale-110 opacity-80 rotate-0"
            )} />
          </div>

          {isDragging && (
            <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-pulse" />
          )}
        </button>
      )}
    </div>
  );
}
