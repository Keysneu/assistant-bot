import { Clock, Trash2, MessageSquare, MoreHorizontal, ChevronDown, ChevronRight, Calendar } from "lucide-react";
import type { Session } from "../lib/api";
import { cn } from "../lib/utils";
import { Button } from "./ui/Button";
import { useState, useMemo } from "react";

interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClearAll: () => void;
  isLoading: boolean;
}

function truncateTitle(title: string, maxLength: number = 25): string {
  if (title.length <= maxLength) return title;
  return title.slice(0, maxLength) + "...";
}

import { Skeleton } from "./ui/Skeleton";

type DateGroup = "today" | "yesterday" | "previous7days" | "older";

const GROUP_LABELS: Record<DateGroup, string> = {
  today: "今天",
  yesterday: "昨天",
  previous7days: "过去 7 天",
  older: "更早",
};

export function SessionList({
  sessions,
  currentSessionId,
  onSelectSession,
  onDeleteSession,
  onClearAll,
  isLoading,
}: SessionListProps) {
  const [expandedGroups, setExpandedGroups] = useState<Record<DateGroup, boolean>>({
    today: true,
    yesterday: true,
    previous7days: true,
    older: false,
  });

  const toggleGroup = (group: DateGroup) => {
    setExpandedGroups(prev => ({ ...prev, [group]: !prev[group] }));
  };

  const groupedSessions = useMemo(() => {
    const groups: Record<DateGroup, Session[]> = {
      today: [],
      yesterday: [],
      previous7days: [],
      older: [],
    };

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterday = today - 86400000;
    const lastWeek = today - 86400000 * 7;

    sessions.forEach(session => {
      const date = new Date(session.last_activity || session.created).getTime();
      if (date >= today) {
        groups.today.push(session);
      } else if (date >= yesterday) {
        groups.yesterday.push(session);
      } else if (date >= lastWeek) {
        groups.previous7days.push(session);
      } else {
        groups.older.push(session);
      }
    });

    return groups;
  }, [sessions]);

  return (
    <div className="flex flex-col h-full">
      {isLoading ? (
        <div className="p-3 space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-3">
              <Skeleton className="h-4 w-4 rounded-full flex-shrink-0" />
              <div className="space-y-1 flex-1">
                <Skeleton className="h-4 w-3/4" />
              </div>
            </div>
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center animate-fade-in">
          <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
            <MessageSquare className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">暂无对话历史</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1 p-2">
          {(Object.keys(groupedSessions) as DateGroup[]).map((groupKey) => {
            const groupSessions = groupedSessions[groupKey];
            if (groupSessions.length === 0) return null;

            return (
              <div key={groupKey} className="mb-2">
                <button
                  onClick={() => toggleGroup(groupKey)}
                  className="flex items-center gap-2 w-full px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                >
                  {expandedGroups[groupKey] ? (
                    <ChevronDown className="w-3 h-3" />
                  ) : (
                    <ChevronRight className="w-3 h-3" />
                  )}
                  {GROUP_LABELS[groupKey]}
                  <span className="ml-auto text-[10px] opacity-60 bg-muted px-1.5 py-0.5 rounded-full">
                    {groupSessions.length}
                  </span>
                </button>
                
                {expandedGroups[groupKey] && (
                  <div className="space-y-1 animate-slide-up">
                    {groupSessions.map((session, index) => (
                      <div
                        key={session.id}
                        className={cn(
                          "group relative flex items-center gap-3 px-3 py-2.5 mx-1 rounded-lg cursor-pointer transition-all duration-200",
                          currentSessionId === session.id
                            ? "bg-accent text-accent-foreground shadow-sm"
                            : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
                        )}
                        onClick={() => onSelectSession(session.id)}
                      >
                        <MessageSquare
                          className={cn(
                            "w-4 h-4 flex-shrink-0 transition-colors",
                            currentSessionId === session.id
                              ? "text-primary"
                              : "text-muted-foreground group-hover:text-foreground"
                          )}
                        />
                        <div className="flex-1 min-w-0">
                          <h3
                            className="text-sm truncate font-medium"
                            title={session.title}
                          >
                            {truncateTitle(session.title)}
                          </h3>
                        </div>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center">
                           <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (confirm(`删除对话 "${session.title}"？`)) {
                                  onDeleteSession(session.id);
                                }
                              }}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
