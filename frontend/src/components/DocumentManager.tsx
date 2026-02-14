import { useState, useEffect, useRef, useMemo } from "react";
import {
  FileText,
  Globe,
  Trash2,
  Loader2,
  RefreshCw,
  Plus,
  Upload,
  Link as LinkIcon,
  File,
  X,
  CheckCircle,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown
} from "lucide-react";
import {
  getDocumentList,
  deleteDocument,
  uploadDocument,
  ingestUrls,
} from "../lib/api";
import type { DocumentInfo } from "../types";
import { Button } from "./ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/Card";
import { Input, FloatingLabelInput } from "./ui/Input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import { cn } from "../lib/utils";
import { useToast } from "../hooks/use-toast";

interface DocumentManagerProps {
  onDocumentsChange?: () => void;
}

export function DocumentManager({ onDocumentsChange }: DocumentManagerProps) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [uploadMode, setUploadMode] = useState<"file" | "url">("file");
  const [docToDelete, setDocToDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [urlInput, setUrlInput] = useState("");
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pagination and Sorting state
  const [page, setPage] = useState(1);
  const [sortType, setSortType] = useState<'newest' | 'oldest' | 'name'>('newest');
  const pageSize = 9;

  const sortedDocuments = useMemo(() => {
    return [...documents].sort((a, b) => {
      if (sortType === 'name') return a.source.localeCompare(b.source);
      const dateA = new Date(a.created_at || 0).getTime();
      const dateB = new Date(b.created_at || 0).getTime();
      if (sortType === 'newest') return dateB - dateA;
      return dateA - dateB;
    });
  }, [documents, sortType]);

  const totalPages = Math.ceil(sortedDocuments.length / pageSize);
  const paginatedDocuments = sortedDocuments.slice((page - 1) * pageSize, page * pageSize);

  // Reset page when documents or sort changes
  useEffect(() => {
    setPage(1);
  }, [sortType, documents.length]);

  const loadDocuments = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getDocumentList();
      setDocuments(response.documents);
      setTotalCount(response.total_count);
      setTotalChunks(response.total_chunks);
    } catch (err) {
      setError("加载文档列表失败");
      console.error("Failed to load documents:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleFileSelect = async (file: File) => {
    if (!file) return;

    setIsUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await uploadDocument(file);
      if (result.status === "ready") {
        setSuccessMsg(`文档 "${file.name}" 上传成功`);
        await loadDocuments();
        onDocumentsChange?.();
      } else {
        setError(result.status);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传文档失败");
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleAddUrl = async () => {
    const url = urlInput.trim();
    if (!url) return;

    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setError("请输入有效的 URL");
      return;
    }

    setIsAddingUrl(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await ingestUrls([url]);
      // 检查第一个文档的状态
      const firstDoc = result.documents?.[0];
      if (firstDoc && firstDoc.status === "ready") {
        setSuccessMsg(`URL "${url}" 添加成功，已处理 ${firstDoc.chunk_count || 0} 个片段`);
        setUrlInput("");
        await loadDocuments();
        onDocumentsChange?.();
        // 成功后关闭对话框
        setAddDialogOpen(false);
      } else if (firstDoc?.status?.startsWith("failed")) {
        setError(firstDoc.status);
      } else {
        setError("添加 URL 失败");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加 URL 失败");
    } finally {
      setIsAddingUrl(false);
    }
  };

  const confirmDelete = (docId: string) => {
    setDocToDelete(docId);
    setDeleteConfirmOpen(true);
  };

  const handleDelete = async () => {
    if (!docToDelete) return;
    
    setIsDeleting(docToDelete);
    setError(null);
    try {
      await deleteDocument(docToDelete);
      setSuccessMsg("文档删除成功");
      setDeleteConfirmOpen(false);
      await loadDocuments();
      onDocumentsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除文档失败");
    } finally {
      setIsDeleting(null);
      setDocToDelete(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8 space-y-6 animate-fade-in">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-3">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">文档总数</CardTitle>
                    <FileText className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{totalCount}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">知识片段</CardTitle>
                    <RefreshCw className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{totalChunks}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">状态</CardTitle>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold text-green-500">正常</div>
                </CardContent>
            </Card>
        </div>

        {/* Feedback Messages */}
        {error && (
            <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg flex items-center gap-2 text-sm animate-fade-in">
                <AlertCircle className="h-4 w-4" />
                {error}
            </div>
        )}
        {successMsg && (
            <div className="bg-green-500/10 text-green-600 px-4 py-3 rounded-lg flex items-center gap-2 text-sm animate-fade-in">
                <CheckCircle className="h-4 w-4" />
                {successMsg}
            </div>
        )}

        {/* Documents List */}
        <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <h3 className="text-lg font-semibold">已收录文档</h3>
                <div className="flex items-center gap-2">
                    <Button onClick={() => setAddDialogOpen(true)} size="sm" className="gap-2">
                        <Plus className="h-4 w-4" />
                        添加文档
                    </Button>
                    <div className="w-px h-6 bg-border mx-1" />
                    <div className="flex items-center bg-muted rounded-lg p-1">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            className={cn("h-7 px-3 text-xs", sortType === 'newest' && "bg-background shadow-sm")}
                            onClick={() => setSortType('newest')}
                        >
                            最新
                        </Button>
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            className={cn("h-7 px-3 text-xs", sortType === 'oldest' && "bg-background shadow-sm")}
                            onClick={() => setSortType('oldest')}
                        >
                            最早
                        </Button>
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            className={cn("h-7 px-3 text-xs", sortType === 'name' && "bg-background shadow-sm")}
                            onClick={() => setSortType('name')}
                        >
                            名称
                        </Button>
                    </div>
                    <Button variant="ghost" size="sm" onClick={loadDocuments} disabled={isLoading}>
                        <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} />
                        刷新
                    </Button>
                </div>
            </div>

            {isLoading ? (
                <div className="flex flex-col items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 text-primary animate-spin" />
                    <p className="text-sm text-muted-foreground mt-2">加载中...</p>
                </div>
            ) : documents.length === 0 ? (
                 <div className="text-center py-12 border rounded-lg bg-muted/10 border-dashed">
                    <p className="text-muted-foreground">暂无文档，请上传或添加 URL</p>
                </div>
            ) : (
                <>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 animate-in fade-in-0 slide-in-from-bottom-4">
                    {paginatedDocuments.map((doc, idx) => (
                        <Card 
                            key={doc.document_id} 
                            className="group hover:shadow-md transition-all duration-300 animate-slide-up"
                            style={{ animationDelay: `${idx * 50}ms` }}
                        >
                            <CardContent className="p-4 flex flex-col h-full justify-between gap-4">
                                <div className="flex items-start gap-3">
                                    <div className="p-2 rounded bg-primary/10 text-primary">
                                        {doc.file_type === "url" ? <Globe className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <h4 className="font-medium text-sm truncate" title={doc.source}>
                                            {doc.source}
                                        </h4>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            {doc.chunk_count} 片段 · {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : "未知时间"}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex justify-end pt-2 border-t border-border mt-2">
                                     <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-destructive hover:text-destructive hover:bg-destructive/10 h-8 px-2"
                                        onClick={() => confirmDelete(doc.document_id)}
                                        disabled={isDeleting === doc.document_id}
                                    >
                                        {isDeleting === doc.document_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                                        <span className="ml-2 text-xs">删除</span>
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
                {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2 mt-6 animate-fade-in">
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            className="h-8 w-8"
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-sm text-muted-foreground">
                            {page} / {totalPages}
                        </span>
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page === totalPages}
                            className="h-8 w-8"
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                )}
                </>
            )}
        </div>

        <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>确认删除文档</DialogTitle>
                    <DialogDescription>
                        此操作无法撤销。这将永久删除该文档及其所有知识片段。
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)} disabled={!!isDeleting}>
                        取消
                    </Button>
                    <Button variant="destructive" onClick={handleDelete} disabled={!!isDeleting}>
                        {isDeleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                        确认删除
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>

        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>添加知识库文档</DialogTitle>
                    <DialogDescription>
                        上传文件或抓取网页内容以扩充知识库
                    </DialogDescription>
                </DialogHeader>
                
                <div className="flex gap-2 p-1 bg-muted rounded-lg mb-4">
                    <button
                        className={cn(
                            "flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-md transition-all",
                            uploadMode === "file" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                        )}
                        onClick={() => setUploadMode("file")}
                    >
                        <Upload className="h-4 w-4" />
                        上传文件
                    </button>
                    <button
                        className={cn(
                            "flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium rounded-md transition-all",
                            uploadMode === "url" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                        )}
                        onClick={() => setUploadMode("url")}
                    >
                        <Globe className="h-4 w-4" />
                        添加 URL
                    </button>
                </div>

                {uploadMode === "file" ? (
                    <div className="flex flex-col items-center justify-center py-8 border-2 border-dashed rounded-lg bg-muted/30">
                        <div className="p-4 rounded-full bg-primary/10 mb-4">
                            <Upload className="h-8 w-8 text-primary" />
                        </div>
                        <h3 className="text-lg font-semibold mb-1">点击或拖拽上传</h3>
                        <p className="text-sm text-muted-foreground mb-6">
                            支持 PDF, TXT, Markdown 格式
                        </p>
                        <Button onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
                            {isUploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
                            选择文件
                        </Button>
                        <input
                            type="file"
                            ref={fileInputRef}
                            className="hidden"
                            accept=".txt,.md,.pdf"
                            onChange={(e) => {
                                handleFileUpload(e);
                                setAddDialogOpen(false);
                            }}
                        />
                    </div>
                ) : (
                    <div className="space-y-4 py-4">
                        <FloatingLabelInput
                            label="网页链接 (https://...)"
                            value={urlInput}
                            onChange={(e) => setUrlInput(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                            系统将自动抓取该网页的正文内容并添加到知识库中。
                        </p>
                        <Button
                            onClick={() => handleAddUrl()}
                            disabled={isAddingUrl || !urlInput}
                            className="w-full"
                        >
                            {isAddingUrl ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Globe className="mr-2 h-4 w-4" />}
                            开始抓取
                        </Button>
                    </div>
                )}
            </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
