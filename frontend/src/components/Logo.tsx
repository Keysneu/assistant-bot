import { cn } from "../lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function Logo({ className, size = "md" }: LogoProps) {
  const sizeClasses = {
    sm: "w-6 h-6",
    md: "w-8 h-8",
    lg: "w-10 h-10"
  };

  return (
    <img
      src="/logo.png"
      alt="AssistantBot Logo"
      className={cn(
        "rounded-lg object-contain",
        sizeClasses[size],
        className
      )}
    />
  );
}
