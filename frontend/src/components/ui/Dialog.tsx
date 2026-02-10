import * as React from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { cn } from "../../lib/utils"

interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

const DialogContext = React.createContext<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>({ open: false, onOpenChange: () => {} });

export const Dialog: React.FC<DialogProps> = ({ open, onOpenChange, children }) => {
  const [isOpen, setIsOpen] = React.useState(open || false);

  React.useEffect(() => {
    if (open !== undefined) {
      setIsOpen(open);
    }
  }, [open]);

  const handleOpenChange = (newOpen: boolean) => {
    setIsOpen(newOpen);
    onOpenChange?.(newOpen);
  };

  return (
    <DialogContext.Provider value={{ open: isOpen, onOpenChange: handleOpenChange }}>
      {children}
    </DialogContext.Provider>
  );
};

export const DialogTrigger: React.FC<{ asChild?: boolean; children: React.ReactNode; onClick?: () => void; className?: string }> = ({ asChild, children, onClick, className }) => {
  const { onOpenChange } = React.useContext(DialogContext);
  return (
    <div 
      className={cn("inline-block", className)}
      onClick={(e) => {
        onClick?.();
        onOpenChange(true);
      }}
    >
      {children}
    </div>
  );
};

export const DialogContent: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => {
  const { open, onOpenChange } = React.useContext(DialogContext);
  const [visible, setVisible] = React.useState(open);
  const [animating, setAnimating] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setVisible(true);
      setAnimating(true);
    } else if (visible) {
      setAnimating(true);
      const timer = setTimeout(() => {
        setVisible(false);
        setAnimating(false);
      }, 300); // Animation duration matches CSS
      return () => clearTimeout(timer);
    }
  }, [open, visible]);

  if (!visible && !animating) return null;

  return createPortal(
    <div className={cn("fixed inset-0 z-50 flex items-center justify-center")}>
      {/* Backdrop */}
      <div 
        className={cn(
          "fixed inset-0 bg-background/80 backdrop-blur-sm transition-all duration-300",
          open ? "opacity-100" : "opacity-0"
        )}
        onClick={() => onOpenChange(false)}
      />
      
      {/* Content */}
      <div 
        className={cn(
          "relative z-50 w-full max-w-lg gap-4 border bg-card p-6 shadow-lg duration-300 sm:rounded-xl",
          open 
            ? "animate-in fade-in-0 zoom-in-95 slide-in-from-bottom-[48%]" 
            : "animate-out fade-out-0 zoom-out-95 slide-out-to-bottom-[48%]",
           className
        )}
      >
         <button
          className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground cursor-pointer"
          onClick={() => onOpenChange(false)}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </button>
        {children}
      </div>
    </div>,
    document.body
  );
};

export const DialogHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <div className={cn("flex flex-col space-y-1.5 text-center sm:text-left mb-4", className)}>
    {children}
  </div>
);

export const DialogFooter: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <div className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 mt-6", className)}>
    {children}
  </div>
);

export const DialogTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <h2 className={cn("text-lg font-semibold leading-none tracking-tight", className)}>
    {children}
  </h2>
);

export const DialogDescription: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <p className={cn("text-sm text-muted-foreground mt-1", className)}>
    {children}
  </p>
);
