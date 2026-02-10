import { useState, useEffect, useCallback, useRef } from "react";
import type { Session, SessionDetail } from "../lib/api";
import {
  getSessions,
  getSession,
  createSession,
  updateSessionTitle,
  deleteSession,
  clearAllSessions,
} from "../lib/api";

const CURRENT_SESSION_KEY = "assistantbot_current_session";

// 检查错误是否为网络错误
function isNetworkError(err: unknown): boolean {
  if (err instanceof TypeError) {
    return err.message.includes("Failed to fetch") ||
           err.message.includes("NetworkError");
  }
  return false;
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isBackendAvailable, setIsBackendAvailable] = useState(true);

  // 使用 ref 来跟踪是否已经尝试过连接
  const hasAttemptedConnection = useRef(false);

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await getSessions();
      setSessions(response.sessions);
      setError(null);
      setIsBackendAvailable(true);
    } catch (err) {
      // 网络错误时不设置 error，只标记后端不可用
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        // 只在第一次尝试时打印警告
        if (!hasAttemptedConnection.current) {
          console.warn("后端服务器未运行，会话功能暂时不可用");
          hasAttemptedConnection.current = true;
        }
      } else {
        setError(err instanceof Error ? err.message : "加载会话失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 加载当前会话详情
  const loadCurrentSession = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    try {
      const session = await getSession(sessionId);
      setCurrentSession(session);
      setError(null);
      setIsBackendAvailable(true);
      return session;
    } catch (err) {
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        // 清空当前会话显示，避免显示过时数据
        setCurrentSession(null);
      } else {
        setError(err instanceof Error ? err.message : "加载会话详情失败");
      }
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 创建新会话
  const createNewSession = useCallback(async (title?: string) => {
    setIsLoading(true);
    try {
      const response = await createSession(title);
      const newSessionId = response.session_id;
      setCurrentSessionId(newSessionId);
      localStorage.setItem(CURRENT_SESSION_KEY, newSessionId);
      setIsBackendAvailable(true);
      setError(null);
      await loadSessions();
      return newSessionId;
    } catch (err) {
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        setError("后端服务器未连接，无法创建会话");
      } else {
        setError(err instanceof Error ? err.message : "创建会话失败");
      }
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [loadSessions]);

  // 切换会话
  const switchSession = useCallback(async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    localStorage.setItem(CURRENT_SESSION_KEY, sessionId);
    const session = await loadCurrentSession(sessionId);
    return session;
  }, [loadCurrentSession]);

  // 更新会话标题
  const renameSession = useCallback(async (sessionId: string, title: string) => {
    setIsLoading(true);
    try {
      await updateSessionTitle(sessionId, title);
      setIsBackendAvailable(true);
      setError(null);
      await loadSessions();
      if (currentSession?.session_id === sessionId) {
        setCurrentSession(prev => prev ? { ...prev, title } : null);
      }
    } catch (err) {
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        setError("后端服务器未连接");
      } else {
        setError(err instanceof Error ? err.message : "更新标题失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, [loadSessions, currentSession]);

  // 删除会话
  const removeSession = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    try {
      await deleteSession(sessionId);
      setIsBackendAvailable(true);
      setError(null);
      await loadSessions();
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setCurrentSession(null);
        localStorage.removeItem(CURRENT_SESSION_KEY);
      }
    } catch (err) {
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        setError("后端服务器未连接");
      } else {
        setError(err instanceof Error ? err.message : "删除会话失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, [loadSessions, currentSessionId]);

  // 清空所有会话
  const clearSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      await clearAllSessions();
      setIsBackendAvailable(true);
      setError(null);
      setSessions([]);
      setCurrentSessionId(null);
      setCurrentSession(null);
      localStorage.removeItem(CURRENT_SESSION_KEY);
    } catch (err) {
      if (isNetworkError(err)) {
        setIsBackendAvailable(false);
        setError("后端服务器未连接");
      } else {
        setError(err instanceof Error ? err.message : "清空会话失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 初始化：只加载保存的会话 ID，延迟加载会话列表
  useEffect(() => {
    const savedSessionId = localStorage.getItem(CURRENT_SESSION_KEY);
    if (savedSessionId) {
      setCurrentSessionId(savedSessionId);
    }
    // 延迟加载，避免页面刚加载时的错误
    const timer = setTimeout(() => {
      loadSessions();
    }, 100);
    return () => clearTimeout(timer);
  }, [loadSessions]);

  // 当 currentSessionId 变化时，加载会话详情
  useEffect(() => {
    if (currentSessionId && isBackendAvailable) {
      loadCurrentSession(currentSessionId);
    } else if (!currentSessionId) {
      setCurrentSession(null);
    }
  }, [currentSessionId, loadCurrentSession, isBackendAvailable]);

  return {
    sessions,
    currentSessionId,
    currentSession,
    isLoading,
    error,
    isBackendAvailable,
    loadSessions,
    loadCurrentSession,
    createNewSession,
    switchSession,
    renameSession,
    removeSession,
    clearSessions,
    setCurrentSessionId,
  };
}
