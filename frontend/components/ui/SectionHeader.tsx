interface SectionHeaderProps {
  title: string;
  className?: string;
}

export default function SectionHeader({ title, className = "" }: SectionHeaderProps) {
  return (
    <h2 className={`text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4 ${className}`}>
      {title}
    </h2>
  );
}
