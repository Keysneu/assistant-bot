import { useState, useEffect, Suspense, lazy } from "react";
// import { ChatBox } from "./components/ChatBox";
// import { DocumentManager } from "./components/DocumentManager";
import { SessionList } from "./components/SessionList";
import { healthCheck } from "./lib/api";
import type { HealthResponse } from "./types";
import {
  MessageSquare,
  FileText,
  Plus,
  PanelLeftClose,
  PanelLeft,
  LayoutDashboard,
  Settings,
  ChevronRight,
  Loader2,
} from "lucide-react";

const ChatBox = lazy(() => import("./components/ChatBox").then(module => ({ default: module.ChatBox })));
const DocumentManager = lazy(() => import("./components/DocumentManager").then(module => ({ default: module.DocumentManager })));

import { useSessions } from "./hooks/useSessions";
import { cn } from "./lib/utils";
import { Button } from "./components/ui/Button";

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  const {
    sessions,
    currentSessionId,
    isLoading: sessionsLoading,
    createNewSession,
    switchSession,
    removeSession,
    clearSessions,
    loadSessions,
  } = useSessions();

  const currentSessionTitle = sessions.find(s => s.id === currentSessionId)?.title;

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const status = await healthCheck();
        setHealth(status);
      } catch (e) {
        setHealth({
          status: "error",
          version: "0.1.0",
          model_loaded: false,
          embedding_loaded: false,
          vector_db_ready: false,
        });
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (activeTab === "chat") {
      loadSessions();
    }
  }, [activeTab, loadSessions]);

  const handleNewChat = async () => {
    await createNewSession();
    if (isMobile) setSidebarOpen(false);
  };

  const handleSelectSession = async (sessionId: string) => {
    await switchSession(sessionId);
    if (isMobile) setSidebarOpen(false);
  };

  return (
    <div className="h-screen flex bg-background text-foreground overflow-hidden font-sans">
      {/* Mobile Overlay */}
      {isMobile && sidebarOpen && (
        <div 
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed md:relative z-50 h-full bg-card border-r border-border transition-all duration-300 ease-in-out flex flex-col shadow-lg md:shadow-none",
          sidebarOpen ? "translate-x-0 w-72" : "-translate-x-full md:translate-x-0 md:w-0 md:border-none md:overflow-hidden"
        )}
      >
        {/* Sidebar Header */}
        <div className="h-14 flex items-center justify-between px-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2 font-semibold text-lg tracking-tight">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground">
              <MessageSquare className="w-5 h-5" />
            </div>
            <span>AssistantBot</span>
          </div>
          {isMobile && (
             <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)}>
               <PanelLeftClose className="w-5 h-5" />
             </Button>
          )}
        </div>

        {/* Sidebar Actions */}
        <div className="p-3 space-y-2 flex-shrink-0">
          <Button 
            onClick={handleNewChat} 
            className="w-full justify-start gap-2 shadow-sm"
            size="lg"
          >
            <Plus className="w-5 h-5" />
            新建对话
          </Button>
        </div>

        {/* Navigation Tabs */}
        <div className="px-3 pb-2 flex-shrink-0">
          <div className="flex bg-muted p-1 rounded-lg">
            <button
              onClick={() => setActiveTab("chat")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-1.5 text-sm font-medium rounded-md transition-all duration-200",
                activeTab === "chat" 
                  ? "bg-background text-foreground shadow-sm" 
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <MessageSquare className="w-4 h-4" />
              对话
            </button>
            <button
              onClick={() => setActiveTab("documents")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-1.5 text-sm font-medium rounded-md transition-all duration-200",
                activeTab === "documents" 
                  ? "bg-background text-foreground shadow-sm" 
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <FileText className="w-4 h-4" />
              知识库
            </button>
          </div>
        </div>

        {/* Sidebar Content (Session List) */}
        <div className="flex-1 overflow-hidden">
          {activeTab === "chat" && (
            <SessionList
              sessions={sessions}
              currentSessionId={currentSessionId}
              onSelectSession={handleSelectSession}
              onDeleteSession={removeSession}
              onClearAll={clearSessions}
              isLoading={sessionsLoading}
            />
          )}
          {activeTab === "documents" && (
            <div className="p-4 text-sm text-muted-foreground text-center mt-10">
              <FileText className="w-10 h-10 mx-auto mb-2 opacity-50" />
              <p>请在主界面管理文档</p>
            </div>
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-border flex items-center justify-between text-xs text-muted-foreground flex-shrink-0 bg-muted/20">
          <div className="flex items-center gap-2">
            <div className={cn("w-2 h-2 rounded-full", health?.status === "healthy" ? "bg-green-500 animate-pulse" : "bg-red-500")} />
            <span>{health?.status === "healthy" ? "系统正常" : "服务异常"}</span>
          </div>
          <span>v{health?.version || "0.1.0"}</span>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-background relative z-0">
        {/* Header (Desktop only or shared) */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-border bg-background/80 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className={cn("text-muted-foreground", sidebarOpen && !isMobile ? "md:hidden" : "")}
            >
              {sidebarOpen ? <PanelLeftClose className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
            </Button>
            
            {/* Breadcrumbs */}
            <div className="flex items-center text-sm font-medium">
              <span className="text-muted-foreground">AssistantBot</span>
              <ChevronRight className="w-4 h-4 text-muted-foreground mx-1" />
              {activeTab === "chat" ? (
                <>
                  <span className={cn(currentSessionId ? "text-muted-foreground" : "text-foreground")}>对话</span>
                  {currentSessionId && (
                    <>
                      <ChevronRight className="w-4 h-4 text-muted-foreground mx-1" />
                      <span className="text-foreground max-w-[150px] sm:max-w-[300px] truncate">
                        {currentSessionTitle || "加载中..."}
                      </span>
                    </>
                  )}
                </>
              ) : (
                <span className="text-foreground">知识库管理</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="text-muted-foreground">
               <Settings className="w-5 h-5" />
            </Button>
          </div>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden relative">
          <Suspense fallback={
            <div className="h-full flex items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          }>
            {activeTab === "chat" ? (
              <ChatBox
                sessionId={currentSessionId || undefined}
                onSessionChange={switchSession}
                onRefreshSessions={loadSessions}
              />
            ) : (
              <DocumentManager />
            )}
          </Suspense>
        </div>
      </main>
    </div>
  );
}

export default App;
