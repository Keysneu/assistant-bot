import * as React from "react";
import { cn } from "../../lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
    error?: boolean;
  }

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, error, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 hover:border-primary/50",
          error && "border-destructive focus-visible:ring-destructive",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

interface FloatingLabelInputProps extends InputProps {
  label: string;
}

const FloatingLabelInput = React.forwardRef<HTMLInputElement, FloatingLabelInputProps>(
  ({ className, label, id, error, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id || generatedId;

    return (
      <div className="relative">
        <Input
          ref={ref}
          id={inputId}
          className={cn("peer pt-5 pb-2 h-11", className)}
          placeholder=" "
          error={error}
          {...props}
        />
        <label
          htmlFor={inputId}
          className={cn(
            "absolute left-3 top-1 text-xs text-muted-foreground transition-all duration-200 pointer-events-none origin-[0]",
            "peer-placeholder-shown:top-3 peer-placeholder-shown:text-sm peer-placeholder-shown:text-muted-foreground",
            "peer-focus:top-1 peer-focus:text-xs peer-focus:text-primary",
            error && "text-destructive peer-focus:text-destructive peer-placeholder-shown:text-destructive"
          )}
        >
          {label}
        </label>
      </div>
    );
  }
);
FloatingLabelInput.displayName = "FloatingLabelInput";

export { Input, FloatingLabelInput };
