import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Loader2, User, Bot, AlertCircle } from "lucide-react";
import type { ChatMessage } from "../types";
import { streamMessage, getSession } from "../lib/api";
import { cn } from "../lib/utils";
import { Button } from "./ui/Button";
import { Skeleton } from "./ui/Skeleton";
import { Card } from "./ui/Card";
import { ImageUploader } from "./ImageUploader";

interface ChatBoxProps {
  sessionId?: string;
  onSessionChange?: (sessionId: string) => void;
  onRefreshSessions?: () => void;
}

function isNetworkError(err: unknown): boolean {
  if (err instanceof TypeError) {
    return (
      err.message.includes("Failed to fetch") ||
      err.message.includes("NetworkError")
    );
  }
  return false;
}

export function ChatBox({
  sessionId,
  onSessionChange,
  onRefreshSessions,
}: ChatBoxProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isBackendAvailable, setIsBackendAvailable] = useState(true);
  // Multimodal state
  const [selectedImageData, setSelectedImageData] = useState("");
  const [selectedImageFormat, setSelectedImageFormat] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const hasAttemptedConnection = useRef(false);

  useEffect(() => {
    const loadSessionHistory = async () => {
      if (sessionId) {
        setIsLoadingHistory(true);
        try {
          const session = await getSession(sessionId);
          const historyMessages = session.messages.map((msg) => ({
            role: msg.role as "user" | "assistant",
            content: msg.content,
            timestamp: new Date(msg.timestamp),
            // 多模态支持：保留图片相关字段
            has_image: msg.has_image,
            image_data: msg.image_data,
            image_format: msg.image_format,
          }));
          setMessages(historyMessages);
          setIsBackendAvailable(true);
        } catch (error) {
          if (isNetworkError(error)) {
            setIsBackendAvailable(false);
            if (!hasAttemptedConnection.current) {
              console.warn("后端服务器未运行");
              hasAttemptedConnection.current = true;
            }
          } else {
            console.error("加载会话历史失败:", error);
          }
          setMessages([]);
        } finally {
          setIsLoadingHistory(false);
        }
      } else {
        setMessages([]);
      }
    };

    loadSessionHistory();
  }, [sessionId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && !selectedImageData) || isLoading) return;

    if (!isBackendAvailable) {
      setIsLoading(true);
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "⚠️ 后端服务器未连接，请先启动后端服务。",
            timestamp: new Date(),
          },
        ]);
        setIsLoading(false);
      }, 500);
      setInput("");
      setSelectedImageData("");
      setSelectedImageFormat("");
      return;
    }

    const userMessage: ChatMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
      has_image: !!selectedImageData,
      image_data: selectedImageData || undefined,
      image_format: selectedImageFormat || undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    const messageToSend = input.trim();
    const imageDataToSend = selectedImageData;
    const imageFormatToSend = selectedImageFormat;

    setInput("");
    setSelectedImageData("");
    setSelectedImageFormat("");
    setIsLoading(true);

    const assistantMessage: ChatMessage = {
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      let fullResponse = "";
      let newSessionId: string | null = null;

      for await (const token of streamMessage(
        messageToSend,
        sessionId,
        imageDataToSend,
        imageFormatToSend,
      )) {
        try {
          const parsed = JSON.parse(token);
          if (parsed.session_id) {
            newSessionId = parsed.session_id;
            if (onSessionChange && newSessionId && newSessionId !== sessionId) {
              onSessionChange(newSessionId);
            }
          }
        } catch {
          fullResponse += token;
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              ...newMessages[newMessages.length - 1],
              content: fullResponse,
            };
            return newMessages;
          });
        }
      }

      setIsBackendAvailable(true);

      if (onRefreshSessions) {
        onRefreshSessions();
      }
    } catch (error) {
      if (isNetworkError(error)) {
        setIsBackendAvailable(false);
      }
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          ...newMessages[newMessages.length - 1],
          content: isNetworkError(error)
            ? "⚠️ 后端服务器未连接，请先启动后端服务。"
            : `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
        };
        return newMessages;
      });
    } finally {
      setIsLoading(false);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const renderMarkdown = (content: string) => {
    return (
      <div className="markdown-content prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({ className, children, ...props }: any) {
              const isInline = !children?.toString().includes("\n");
              return (
                <code
                  className={cn(
                    isInline
                      ? "bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground"
                      : "block bg-muted/50 p-4 rounded-lg text-sm overflow-x-auto font-mono my-2 border border-border",
                    className
                  )}
                  {...props}
                >
                  {children}
                </code>
              );
            },
            pre({ children }: any) {
              return <>{children}</>;
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-background relative">
      {/* Messages Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-smooth">
        <div className="max-w-3xl mx-auto px-4 py-8 space-y-8">
          {/* Connection Warning */}
          {!isBackendAvailable && (
            <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-3 animate-fade-in">
              <AlertCircle className="w-5 h-5 text-destructive" />
              <p className="text-sm text-destructive-foreground font-medium">
                后端服务器未连接，请先启动后端服务
              </p>
            </div>
          )}

          {/* Loading State */}
          {isLoadingHistory ? (
            <div className="space-y-6 py-4 animate-fade-in">
              {[1, 2, 3].map((i) => (
                <div key={i} className={cn("flex gap-4", i % 2 === 0 ? "justify-end" : "justify-start")}>
                   {i % 2 !== 0 && (
                     <Skeleton className="w-8 h-8 rounded-lg flex-shrink-0" />
                   )}
                   <div className={cn("space-y-2", i % 2 === 0 ? "items-end" : "items-start")}>
                     <Skeleton className={cn("h-10 w-[250px] sm:w-[350px]", i % 2 === 0 ? "rounded-tr-sm" : "rounded-tl-sm")} />
                     <Skeleton className="h-4 w-[150px] opacity-60" />
                   </div>
                   {i % 2 === 0 && (
                     <Skeleton className="w-8 h-8 rounded-lg flex-shrink-0" />
                   )}
                </div>
              ))}
            </div>
          ) : messages.length === 0 ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center py-20 text-center animate-slide-up">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 shadow-sm">
                <Bot className="w-8 h-8 text-primary" />
              </div>
              <h2 className="text-2xl font-semibold text-foreground mb-3">
                {sessionId ? "开始新对话..." : "你好！我是 AssistantBot"}
              </h2>
              <p className="text-muted-foreground max-w-md mx-auto leading-relaxed">
                {isBackendAvailable
                  ? "我可以帮你搜索知识库、回答问题，或者只是聊聊天。试着问我点什么吧！"
                  : "请先启动后端服务以开始对话"}
              </p>
            </div>
          ) : (
            /* Messages */
            <div className="space-y-6">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "flex gap-4 animate-slide-up",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                      <Bot className="w-5 h-5 text-primary" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[85%] px-5 py-3.5 shadow-sm",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
                        : "bg-card border border-border text-card-foreground rounded-2xl rounded-tl-sm"
                    )}
                  >
                    {/* Display image if present */}
                    {msg.has_image && msg.image_data && (
                      <div className="mb-3 rounded-lg overflow-hidden">
                        <img
                          src={`data:image/${msg.image_format || "png"};base64,${msg.image_data}`}
                          alt="Uploaded image"
                          className="max-w-full h-auto rounded-lg"
                        />
                      </div>
                    )}
                    {msg.role === "assistant" ? (
                      <div className="text-sm leading-relaxed">
                        {msg.content ? renderMarkdown(msg.content) : <span className="animate-pulse">...</span>}
                      </div>
                    ) : (
                      <div>
                        {msg.content && (
                          <p className="text-sm whitespace-pre-wrap leading-relaxed">
                            {msg.content}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0 mt-1">
                      <User className="w-5 h-5 text-secondary-foreground" />
                    </div>
                  )}
                </div>
              ))}
              
              {/* Loading Indicator - 只在最后一条消息有内容时才显示独立的加载动画 */}
              {isLoading && messages[messages.length - 1]?.role === "assistant" && messages[messages.length - 1]?.content && (
                 <div className="flex justify-start gap-4 animate-fade-in">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                      <Bot className="w-5 h-5 text-primary" />
                    </div>
                    <div className="px-5 py-3.5 bg-card border border-border rounded-2xl rounded-tl-sm shadow-sm">
                      <div className="flex items-center gap-1.5 h-5">
                        <div className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.3s]" />
                        <div className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]" />
                        <div className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce" />
                      </div>
                    </div>
                  </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 p-4 bg-background/80 backdrop-blur-sm border-t border-border z-10">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative group"
        >
          <div className={cn(
            "relative flex items-end bg-card border border-input rounded-xl shadow-sm transition-all duration-200",
            "focus-within:ring-2 focus-within:ring-ring focus-within:border-primary focus-within:shadow-md",
            "hover:border-primary/50"
          )}>
            {/* Image uploader */}
            <div className="absolute left-3 bottom-3 z-10">
              <ImageUploader
                onImageSelect={(data, format) => {
                  setSelectedImageData(data);
                  setSelectedImageFormat(format);
                }}
                disabled={isLoading || !isBackendAvailable}
              />
            </div>

            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isBackendAvailable
                  ? "发送消息... (Enter 发送, Shift+Enter 换行)"
                  : "后端服务未启动..."
              }
              className="flex-1 min-h-[52px] max-h-[200px] px-4 py-3.5 bg-transparent text-foreground placeholder:text-muted-foreground resize-none focus:outline-none text-sm leading-relaxed pr-24 pl-14 rounded-xl"
              disabled={isLoading || !isBackendAvailable}
              rows={1}
              style={{
                height: "auto",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 200) + "px";
              }}
            />
            <Button
              type="submit"
              size="icon"
              disabled={(!input.trim() && !selectedImageData) || isLoading || !isBackendAvailable}
              className={cn(
                "absolute right-2 bottom-2 transition-all duration-200 h-8 w-8",
                (input.trim() || selectedImageData) && !isLoading && isBackendAvailable
                  ? "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                  : "bg-muted text-muted-foreground cursor-not-allowed hover:bg-muted"
              )}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground mt-2 text-center opacity-70">
            由 Qwen2.5-7B 驱动 · 支持知识库检索与图片理解
          </p>
        </form>
      </div>
    </div>
  );
}
