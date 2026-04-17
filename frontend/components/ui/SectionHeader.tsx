interface SectionHeaderProps {
  title: string;
  className?: string;
}

export default function SectionHeader({ title, className = "" }: SectionHeaderProps) {
  return (
    <div className={`mb-4 flex items-center gap-3 ${className}`}>
      <h2 className="text-sm md:text-base font-bold text-zinc-100 uppercase tracking-[0.14em] leading-none">
        {title}
      </h2>
      <div className="h-px flex-1 bg-gradient-to-r from-zinc-600/80 via-zinc-700/50 to-transparent" />
    </div>
  );
}
