interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export default function Card({ children, className = "", onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl border border-zinc-800 bg-zinc-900 ${onClick ? "cursor-pointer hover:border-zinc-700 transition-colors" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
