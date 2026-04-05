import { memo, useState, useRef, useEffect } from "react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Loader2, User, AlertCircle, Paperclip, X, Brain, Wrench, Info } from "lucide-react";
import type { ChatMessage, ChatModeConfigResponse } from "../types";
import { streamMessage, getSession, getChatModeConfig, updateChatModeConfig } from "../lib/api";
import { parseThinkingContent } from "../utils/thinkingParser";
import { cn } from "../lib/utils";
import { Button } from "./ui/Button";
import { Skeleton } from "./ui/Skeleton";
import { ImageUploader } from "./ImageUploader";
import { Logo } from "./Logo";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/Dialog";

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

type DeployProfileKey = "rag_text" | "vision" | "full" | "benchmark";
type StreamDonePayload = {
  session_id?: string;
  full_content?: string;
  display_content?: string;
  reasoning_content?: string | null;
  final_content?: string | null;
};

const PROFILE_ORDER: DeployProfileKey[] = ["rag_text", "vision", "full", "benchmark"];
const STREAM_FLUSH_INTERVAL_MS = 50;
const PROFILE_GUIDE: Record<
  DeployProfileKey,
  {
    title: string;
    description: string;
    supportsImage: boolean;
    supportsThinking: boolean;
    supportsToolCalling: boolean;
  }
> = {
  rag_text: {
    title: "文本 RAG 档位",
    description: "优先文本问答与检索，禁用图片与工具调用。",
    supportsImage: false,
    supportsThinking: true,
    supportsToolCalling: false,
  },
  vision: {
    title: "图文档位",
    description: "开启图片理解，适合图文问答，不开启工具调用。",
    supportsImage: true,
    supportsThinking: true,
    supportsToolCalling: false,
  },
  full: {
    title: "全能力档位",
    description: "支持图片、Thinking 与 Tool Calling。",
    supportsImage: true,
    supportsThinking: true,
    supportsToolCalling: true,
  },
  benchmark: {
    title: "压测档位",
    description: "用于稳定压测，关闭图片、Thinking 与 Tool Calling。",
    supportsImage: false,
    supportsThinking: false,
    supportsToolCalling: false,
  },
};

const AssistantContent = memo(function AssistantContent({
  content,
  isStreaming,
  reasoningContent,
  finalContent,
  preferThinkingPanel,
}: {
  content: string;
  isStreaming: boolean;
  reasoningContent?: string;
  finalContent?: string;
  preferThinkingPanel?: boolean;
}) {
  const renderMarkdown = (markdown: string) => (
    <div className="markdown-content prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }: ComponentPropsWithoutRef<"code"> & { children?: ReactNode }) {
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
          pre({ children }: ComponentPropsWithoutRef<"pre">) {
            return <>{children}</>;
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );

  if (reasoningContent || finalContent) {
    const normalizedFinal = (finalContent || content || "").trim();
    const normalizedReasoning = (reasoningContent || "").trim();

    if (!normalizedReasoning) {
      if (isStreaming && !normalizedFinal) {
        return <span className="animate-pulse">...</span>;
      }
      return renderMarkdown(normalizedFinal);
    }

    return (
      <div className="space-y-3">
        <details className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer list-none text-xs text-muted-foreground flex items-center gap-1.5">
            <Brain className="w-3.5 h-3.5" />
            <span>思考过程</span>
          </summary>
          <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
            {renderMarkdown(normalizedReasoning)}
          </div>
        </details>
        {renderMarkdown(normalizedFinal || normalizedReasoning)}
      </div>
    );
  }

  if (isStreaming && preferThinkingPanel) {
    const parsed = parseThinkingContent(content);
    if (!parsed) {
      return (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              <span>思考中...</span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
              {content.trim() ? renderMarkdown(content) : <span className="animate-pulse">正在思考...</span>}
            </div>
          </div>
          <span className="text-xs text-muted-foreground animate-pulse">正在整理最终回答...</span>
        </div>
      );
    }

    if (parsed) {
      const reasoning = parsed.reasoning.trim();
      const answer = parsed.answer.trim();
      const hasReasoning = Boolean(reasoning);
      const hasAnswer = Boolean(answer);

      return (
        <div className="space-y-3">
          <div className="rounded-lg border border-border/80 bg-muted/20 px-3 py-2">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              <span>{hasAnswer ? "思考完成" : "思考中..."}</span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
              {hasReasoning ? renderMarkdown(reasoning) : <span className="animate-pulse">正在思考...</span>}
            </div>
          </div>
          {hasAnswer ? (
            renderMarkdown(answer)
          ) : (
            <span className="text-xs text-muted-foreground animate-pulse">正在整理最终回答...</span>
          )}
        </div>
      );
    }
  }

  if (isStreaming && !content.trim()) {
    return <span className="animate-pulse">...</span>;
  }
  return renderMarkdown(content);
});

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
  const [selectedFileData, setSelectedFileData] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [selectedFileFormat, setSelectedFileFormat] = useState("");
  const [enableThinkingMode, setEnableThinkingMode] = useState(false);
  const [enableToolCallingMode, setEnableToolCallingMode] = useState(false);
  const [isSwitchingProfile, setIsSwitchingProfile] = useState(false);
  const [modeConfig, setModeConfig] = useState<ChatModeConfigResponse | null>(null);
  const [modeWarnings, setModeWarnings] = useState<string[]>([]);
  const [streamingAssistantIndex, setStreamingAssistantIndex] = useState<number | null>(null);
  const [streamingAssistantContent, setStreamingAssistantContent] = useState("");
  const [streamingThinkingPanelLocked, setStreamingThinkingPanelLocked] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasAttemptedConnection = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);
  const streamBufferRef = useRef("");
  const lastStreamFlushAtRef = useRef(0);

  useEffect(() => {
    const loadModeConfig = async () => {
      try {
        const config = await getChatModeConfig();
        setModeConfig(config);
      } catch (error) {
        console.warn("加载模式配置失败，使用默认能力", error);
      }
    };
    loadModeConfig();
  }, []);

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
            has_file: msg.has_file,
            file_name: msg.file_name,
            file_format: msg.file_format,
            reasoning_content: msg.reasoning_content,
            final_content: msg.final_content,
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
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (streamingAssistantIndex !== null && streamingAssistantContent) {
      scrollToBottom();
    }
  }, [streamingAssistantContent, streamingAssistantIndex]);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && !selectedImageData && !selectedFileData) || isLoading) return;

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
      setSelectedFileData("");
      setSelectedFileName("");
      setSelectedFileFormat("");
      return;
    }

    const userMessage: ChatMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
      has_image: !!selectedImageData,
      image_data: selectedImageData || undefined,
      image_format: selectedImageFormat || undefined,
      has_file: !!selectedFileData,
      file_name: selectedFileName || undefined,
      file_format: selectedFileFormat || undefined,
    };
    const messageToSend = input.trim();
    const imageDataToSend = selectedImageData;
    const imageFormatToSend = selectedImageFormat;
    const fileDataToSend = selectedFileData;
    const fileNameToSend = selectedFileName;
    const fileFormatToSend = selectedFileFormat;

    setInput("");
    setSelectedImageData("");
    setSelectedImageFormat("");
    setSelectedFileData("");
    setSelectedFileName("");
    setSelectedFileFormat("");
    setIsLoading(true);

    const assistantMessage: ChatMessage = {
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    const assistantIndex = messagesRef.current.length + 1;
    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setStreamingAssistantIndex(assistantIndex);
    setStreamingAssistantContent("");
    setStreamingThinkingPanelLocked(Boolean(modeConfig?.supports_thinking ? enableThinkingMode : false));
    streamBufferRef.current = "";
    lastStreamFlushAtRef.current = 0;

    try {
      let fullResponse = "";
      const streamResult: { done: StreamDonePayload | null } = { done: null };
      setModeWarnings([]);

      for await (const token of streamMessage(
        messageToSend,
        sessionId,
        imageDataToSend,
        imageFormatToSend,
        fileDataToSend,
        fileNameToSend,
        fileFormatToSend,
        modeConfig?.supports_thinking ? enableThinkingMode : false,
        modeConfig?.supports_tool_calling ? enableToolCallingMode : false,
        modeConfig?.deploy_profile,
        (metadata) => {
          const newSessionId = metadata.session_id;
          if (onSessionChange && newSessionId && newSessionId !== sessionId) {
            onSessionChange(newSessionId);
          }
          if (Array.isArray(metadata.mode_warnings) && metadata.mode_warnings.length) {
            setModeWarnings(metadata.mode_warnings.map((item) => String(item)));
          }
          if (typeof metadata.enable_thinking === "boolean") {
            setStreamingThinkingPanelLocked(metadata.enable_thinking);
          }
          if (imageDataToSend && metadata.multimodal_mode && metadata.multimodal_mode !== "gemma4_native") {
            setModeWarnings((prev) => {
              const next = [...prev, `图片请求未走 Gemma4 原生多模态链路（当前: ${metadata.multimodal_mode}）`];
              return Array.from(new Set(next));
            });
          }
        },
        (done) => {
          streamResult.done = done;
        },
      )) {
        fullResponse += token;
        streamBufferRef.current = fullResponse;
        const now = Date.now();
        if (now - lastStreamFlushAtRef.current >= STREAM_FLUSH_INTERVAL_MS) {
          lastStreamFlushAtRef.current = now;
          setStreamingAssistantContent(streamBufferRef.current);
        }
      }

      const displayContent = streamResult.done?.display_content || streamResult.done?.final_content || fullResponse;
      const reasoningContent = streamResult.done?.reasoning_content || undefined;
      const finalContent = streamResult.done?.final_content || streamResult.done?.display_content || displayContent;
      setStreamingAssistantContent(fullResponse);
      setMessages((prev) => {
        const newMessages = [...prev];
        const fallbackIndex = newMessages
          .map((msg, index) => ({ msg, index }))
          .reverse()
          .find((item) => item.msg.role === "assistant")?.index;
        const targetIndex = assistantIndex >= 0 && assistantIndex < newMessages.length
          ? assistantIndex
          : fallbackIndex;
        if (typeof targetIndex === "number") {
          newMessages[targetIndex] = {
            ...newMessages[targetIndex],
            content: displayContent,
            reasoning_content: reasoningContent,
            final_content: finalContent,
          };
        }
        return newMessages;
      });
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
        const fallbackIndex = newMessages
          .map((msg, index) => ({ msg, index }))
          .reverse()
          .find((item) => item.msg.role === "assistant")?.index;
        const targetIndex = assistantIndex >= 0 && assistantIndex < newMessages.length
          ? assistantIndex
          : fallbackIndex;
        if (typeof targetIndex === "number") {
          newMessages[targetIndex] = {
            ...newMessages[targetIndex],
            content: isNetworkError(error)
              ? "⚠️ 后端服务器未连接，请先启动后端服务。"
              : `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
          };
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
      setStreamingAssistantIndex(null);
      setStreamingAssistantContent("");
      setStreamingThinkingPanelLocked(false);
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

  const switchableProfiles = (modeConfig?.available_profiles || PROFILE_ORDER).filter(
    (profile): profile is DeployProfileKey => profile in PROFILE_GUIDE
  );

  const handleSwitchProfile = async (targetProfile: DeployProfileKey) => {
    if (!modeConfig || modeConfig.provider !== "vllm") {
      return;
    }
    if (modeConfig.deploy_profile === targetProfile) {
      return;
    }

    setIsSwitchingProfile(true);
    try {
      const updated = await updateChatModeConfig(targetProfile);
      setModeConfig(updated);
      setModeWarnings([]);

      if (!updated.supports_image) {
        setSelectedImageData("");
        setSelectedImageFormat("");
      }
      if (!updated.supports_thinking) {
        setEnableThinkingMode(false);
      }
      if (!updated.supports_tool_calling) {
        setEnableToolCallingMode(false);
      }
    } catch (error) {
      console.error("切换模式失败:", error);
      alert(`切换模式失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setIsSwitchingProfile(false);
    }
  };

  const handleSelectFile = async (file: File | null) => {
    if (!file) {
      return;
    }

    const allowed = new Set(["txt", "md", "markdown", "pdf", "csv", "json", "log"]);
    const ext = file.name.includes(".") ? file.name.split(".").pop()?.toLowerCase() || "" : "";
    if (!allowed.has(ext)) {
      alert("暂仅支持 txt/md/pdf/csv/json/log 文件");
      return;
    }

    if (file.size > 6 * 1024 * 1024) {
      alert("文件大小不能超过 6MB");
      return;
    }

    try {
      const base64Data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result;
          if (typeof result !== "string" || !result.includes(",")) {
            reject(new Error("文件读取失败"));
            return;
          }
          resolve(result.split(",", 2)[1]);
        };
        reader.onerror = () => reject(new Error("文件读取失败"));
        reader.readAsDataURL(file);
      });

      setSelectedFileData(base64Data);
      setSelectedFileName(file.name);
      setSelectedFileFormat(ext);
    } catch (error) {
      console.error("文件处理失败:", error);
      alert("文件处理失败，请重试");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const clearSelectedFile = () => {
    setSelectedFileData("");
    setSelectedFileName("");
    setSelectedFileFormat("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const currentProfileGuide =
    modeConfig?.deploy_profile && modeConfig.deploy_profile in PROFILE_GUIDE
      ? PROFILE_GUIDE[modeConfig.deploy_profile as DeployProfileKey]
      : null;

  const imageUploadDisabledReason = !isBackendAvailable
    ? "后端服务未连接"
    : isLoading
      ? "正在生成回复，请稍候"
      : isSwitchingProfile
        ? "正在切换模式，请稍候"
      : modeConfig?.supports_image === false
        ? `当前档位 ${modeConfig.deploy_profile} 不支持图片，请切换到 vision 或 full`
        : undefined;

  const capabilityBadgeClass = (enabled: boolean) =>
    cn(
      "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] border",
      enabled
        ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/30"
        : "bg-muted text-muted-foreground border-border"
    );

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
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 shadow-sm p-3">
                <Logo size="lg" />
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
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1 overflow-hidden">
                      <Logo size="sm" />
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
                        {(() => {
                          const isStreamingMessage = isLoading && streamingAssistantIndex === idx;
                          const contentToRender = isStreamingMessage ? streamingAssistantContent : msg.content;
                          return (
                            <AssistantContent
                              content={contentToRender || ""}
                              isStreaming={isStreamingMessage}
                              reasoningContent={msg.reasoning_content}
                              finalContent={msg.final_content}
                              preferThinkingPanel={isStreamingMessage && streamingThinkingPanelLocked}
                            />
                          );
                        })()}
                      </div>
                    ) : (
                      <div>
                        {msg.has_file && msg.file_name && (
                          <div className="mb-2 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-primary-foreground/20 text-xs">
                            <Paperclip className="w-3 h-3" />
                            <span className="truncate max-w-[220px]" title={msg.file_name}>
                              {msg.file_name}
                            </span>
                          </div>
                        )}
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
          <div className="mb-2 flex items-center gap-2">
            <Button
              type="button"
              variant={enableThinkingMode ? "default" : "outline"}
              size="sm"
              className="h-8 gap-1.5"
              onClick={() => setEnableThinkingMode((value) => !value)}
              disabled={isLoading || isSwitchingProfile || !isBackendAvailable || modeConfig?.supports_thinking === false}
              title={
                modeConfig?.supports_thinking === false
                  ? `当前档位 ${modeConfig.deploy_profile} 不支持 Thinking`
                  : "切换 Thinking 模式"
              }
            >
              <Brain className="w-3.5 h-3.5" />
              Thinking
            </Button>
            <Button
              type="button"
              variant={enableToolCallingMode ? "default" : "outline"}
              size="sm"
              className="h-8 gap-1.5"
              onClick={() => setEnableToolCallingMode((value) => !value)}
              disabled={isLoading || isSwitchingProfile || !isBackendAvailable || modeConfig?.supports_tool_calling === false}
              title={
                modeConfig?.supports_tool_calling === false
                  ? `当前档位 ${modeConfig.deploy_profile} 不支持 Tool Calling`
                  : "切换 Tool Calling 模式"
              }
            >
              <Wrench className="w-3.5 h-3.5" />
              Tool Calling
            </Button>
            {modeConfig && (
              <Dialog>
                <DialogTrigger className="inline-flex">
                  <button
                    type="button"
                    className="text-xs text-muted-foreground px-2 py-1 rounded-md border border-border inline-flex items-center gap-1.5 hover:border-primary/40 hover:text-foreground transition-colors"
                    title="查看档位说明"
                  >
                    <Info className="w-3.5 h-3.5" />
                    Profile: {modeConfig.deploy_profile}
                  </button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>Deploy Profile 说明</DialogTitle>
                    <DialogDescription>
                      当前后端档位：<span className="font-medium text-foreground">{modeConfig.deploy_profile}</span>
                      。图片上传是否可用由该档位决定。
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-2.5">
                    {PROFILE_ORDER.map((profileKey) => {
                      const profile = PROFILE_GUIDE[profileKey];
                      const isActive = modeConfig.deploy_profile === profileKey;
                      return (
                        <div
                          key={profileKey}
                          className={cn(
                            "rounded-lg border p-3",
                            isActive ? "border-primary/50 bg-primary/5" : "border-border bg-card"
                          )}
                        >
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <div className="text-sm font-medium text-foreground">
                              {profileKey}
                              {isActive && (
                                <span className="ml-2 text-[11px] text-primary">当前</span>
                              )}
                            </div>
                            <div className="text-[11px] text-muted-foreground">{profile.title}</div>
                          </div>
                          <p className="text-xs text-muted-foreground mb-2">{profile.description}</p>
                          <div className="flex flex-wrap gap-1.5">
                            <span className={capabilityBadgeClass(profile.supportsImage)}>Image</span>
                            <span className={capabilityBadgeClass(profile.supportsThinking)}>Thinking</span>
                            <span className={capabilityBadgeClass(profile.supportsToolCalling)}>Tool Calling</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    可直接点击输入框上方的档位按钮进行运行时切换。若服务端实际部署能力不足，
                    后端会返回明确错误提示。
                  </p>
                </DialogContent>
              </Dialog>
            )}
          </div>
          {modeConfig?.provider === "vllm" && switchableProfiles.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              {switchableProfiles.map((profileKey) => (
                <Button
                  key={profileKey}
                  type="button"
                  size="sm"
                  variant={modeConfig.deploy_profile === profileKey ? "default" : "outline"}
                  className="h-7 px-2.5 text-xs"
                  disabled={isLoading || isSwitchingProfile || !isBackendAvailable}
                  onClick={() => handleSwitchProfile(profileKey)}
                  title={`切换到 ${profileKey}`}
                >
                  {profileKey}
                </Button>
              ))}
              {isSwitchingProfile && (
                <span className="text-[11px] text-muted-foreground">正在切换...</span>
              )}
            </div>
          )}
          {modeWarnings.length > 0 && (
            <div className="mb-2 text-xs text-amber-600">
              {modeWarnings.join("；")}
            </div>
          )}
          {modeConfig?.supports_image === false && (
            <div className="mb-2 text-xs text-amber-600">
              当前 Profile `{modeConfig.deploy_profile}` 已关闭图片输入。切换到 `vision` / `full` 后可上传图片。
            </div>
          )}
          {currentProfileGuide && (
            <div className="mb-2 text-[11px] text-muted-foreground">
              当前档位能力：Image {currentProfileGuide.supportsImage ? "ON" : "OFF"} / Thinking {currentProfileGuide.supportsThinking ? "ON" : "OFF"} / Tool Calling {currentProfileGuide.supportsToolCalling ? "ON" : "OFF"}
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf,.csv,.json,.log"
            className="hidden"
            disabled={isLoading || isSwitchingProfile || !isBackendAvailable}
            onChange={(e) => handleSelectFile(e.target.files?.[0] || null)}
          />
          <div className="flex items-end gap-4">
            {/* Image uploader - 独立在输入框左侧 */}
            <div className="flex-shrink-0">
              <ImageUploader
                onImageSelect={(data, format) => {
                  setSelectedImageData(data);
                  setSelectedImageFormat(format);
                }}
                disabled={
                  isLoading ||
                  isSwitchingProfile ||
                  !isBackendAvailable ||
                  modeConfig?.supports_image === false
                }
                disabledReason={imageUploadDisabledReason}
              />
            </div>

            <div className="flex-shrink-0">
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || isSwitchingProfile || !isBackendAvailable}
                className={cn(
                  "h-12 w-12 rounded-2xl shadow-sm",
                  selectedFileData && "border-primary text-primary"
                )}
                title="上传文件附件"
              >
                <Paperclip className="w-5 h-5" />
              </Button>
            </div>

            {/* Input wrapper */}
            <div className={cn(
              "relative flex-1 flex items-end bg-card border border-input rounded-2xl shadow-lg transition-all duration-300",
              "focus-within:ring-2 focus-within:ring-ring focus-within:border-primary/50 focus-within:shadow-xl",
              "hover:border-primary/30 hover:shadow-md"
            )}>
              {/* 背景装饰 - 光泽效果 */}
              <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />

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
                className={cn(
                  "flex-1 min-h-[52px] max-h-[200px] px-4 py-3.5 bg-transparent text-foreground placeholder:text-muted-foreground resize-none focus:outline-none text-sm leading-relaxed pr-14 rounded-2xl",
                  selectedFileData && "pb-10"
                )}
                disabled={isLoading || isSwitchingProfile || !isBackendAvailable}
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
              {selectedFileData && selectedFileName && (
                <div className="absolute left-3 bottom-2.5 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs border border-border">
                  <Paperclip className="w-3 h-3" />
                  <span className="max-w-[180px] truncate" title={selectedFileName}>
                    {selectedFileName}
                  </span>
                  <button
                    type="button"
                    onClick={clearSelectedFile}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
              <Button
                type="submit"
                size="icon"
                disabled={(!input.trim() && !selectedImageData && !selectedFileData) || isLoading || isSwitchingProfile || !isBackendAvailable}
                className={cn(
                  "absolute right-2 bottom-2 transition-all duration-300 h-10 w-10 rounded-xl",
                  (input.trim() || selectedImageData || selectedFileData) && !isLoading && !isSwitchingProfile && isBackendAvailable
                    ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105 shadow-lg shadow-primary/20"
                    : "bg-muted text-muted-foreground cursor-not-allowed hover:bg-muted"
                )}
              >
                {isLoading ? (
                  <Loader2 className="w-4.5 h-4.5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground/80 mt-2.5 text-center flex items-center justify-center gap-1.5">
            <span className="inline-flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-primary/60 animate-pulse" />
              支持文本/RAG/图片/文件，并可切换 Thinking 与 Tool Calling 模式
            </span>
          </p>
        </form>
      </div>
    </div>
  );
}
