import * as React from "react"
import { X, CheckCircle, AlertCircle, Info } from "lucide-react"
import { cn } from "../../lib/utils"
import type { ToastProps } from "../../hooks/use-toast"

const Toast = React.forwardRef<
  HTMLDivElement,
  ToastProps & { id: string; onClose: () => void }
>(({ className, variant = "default", title, description, action, open, onClose, ...props }, ref) => {
  const [isExiting, setIsExiting] = React.useState(false)

  React.useEffect(() => {
    if (!open) {
      setIsExiting(true)
      const timer = setTimeout(() => {
        onClose()
      }, 300) // Match animation duration
      return () => clearTimeout(timer)
    }
  }, [open, onClose])

  if (!open && !isExiting) return null

  const Icon = variant === "destructive" ? AlertCircle : variant === "success" ? CheckCircle : Info

  return (
    <div
      ref={ref}
      className={cn(
        "group pointer-events-auto relative flex w-full items-center justify-between space-x-4 overflow-hidden rounded-md border p-6 pr-8 shadow-lg transition-all",
        "data-[swipe=cancel]:translate-x-0 data-[swipe=end]:translate-x-[var(--radix-toast-swipe-end-x)] data-[swipe=move]:translate-x-[var(--radix-toast-swipe-move-x)] data-[swipe=move]:transition-none",
        open && !isExiting ? "animate-in slide-in-from-right-full" : "animate-out slide-out-to-right-full fade-out-80",
        variant === "default" && "border bg-background text-foreground",
        variant === "destructive" &&
          "destructive group border-destructive bg-destructive text-destructive-foreground",
        variant === "success" && "border-green-200 bg-green-50 text-green-900 dark:border-green-900 dark:bg-green-950 dark:text-green-100",
        className
      )}
      {...props}
    >
      <div className="flex gap-3 items-start">
        {variant !== "default" && (
           <Icon className={cn("h-5 w-5 mt-0.5", 
              variant === "destructive" ? "text-destructive-foreground" : 
              variant === "success" ? "text-green-600 dark:text-green-400" : "text-blue-600"
           )} />
        )}
        <div className="grid gap-1">
          {title && <div className="text-sm font-semibold">{title}</div>}
          {description && (
            <div className="text-sm opacity-90">{description}</div>
          )}
        </div>
      </div>
      {action}
      <button
        onClick={() => {
          setIsExiting(true)
          setTimeout(onClose, 300)
        }}
        className={cn(
          "absolute right-2 top-2 rounded-md p-1 text-foreground/50 opacity-0 transition-opacity hover:text-foreground focus:opacity-100 focus:outline-none focus:ring-2 group-hover:opacity-100",
          variant === "destructive" && "text-red-300 hover:text-red-50 focus:ring-red-400 focus:ring-offset-red-600",
          variant === "success" && "text-green-600 hover:text-green-700"
        )}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
})
Toast.displayName = "Toast"

export { Toast }
