"use client";

interface Tab {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
  equalWidth?: boolean;
}

export default function Tabs({ tabs, active, onChange, className = "", equalWidth = false }: TabsProps) {
  return (
    <div
      className={`flex gap-1 rounded-lg bg-zinc-800/50 p-1 overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden ${className}`}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`${equalWidth ? "flex-1 min-w-0 text-center px-2.5 py-2" : "shrink-0 sm:flex-1 px-3 py-1.5"} rounded-md text-sm font-medium whitespace-nowrap transition-all ${
            active === tab.id
              ? "bg-zinc-700 text-zinc-100 shadow"
              : "text-zinc-400 hover:text-zinc-200"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
