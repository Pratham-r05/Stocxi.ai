"use client";

import { useEffect, useMemo, useState } from "react";

interface StockSectionTab {
  id: string;
  label: string;
}

interface StockSectionTabsProps {
  sections: StockSectionTab[];
}

export default function StockSectionTabs({ sections }: StockSectionTabsProps) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");

  const validIds = useMemo(() => new Set(sections.map((s) => s.id)), [sections]);

  useEffect(() => {
    const hashId = window.location.hash.replace("#", "");
    if (hashId && validIds.has(hashId)) {
      setActiveId(hashId);
      return;
    }
    if (sections[0]?.id) setActiveId(sections[0].id);
  }, [sections, validIds]);

  useEffect(() => {
    const elements = sections
      .map((section) => document.getElementById(section.id))
      .filter((el): el is HTMLElement => !!el);

    if (!elements.length) return;

    const updateActiveFromScroll = () => {
      const activationOffset = 160;
      let currentId = elements[0].id;

      for (const el of elements) {
        if (el.getBoundingClientRect().top <= activationOffset) {
          currentId = el.id;
        } else {
          break;
        }
      }

      // Keep the last tab active when user reaches page end.
      const nearBottom =
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 4;
      if (nearBottom) {
        currentId = elements[elements.length - 1].id;
      }

      setActiveId((prev) => (prev === currentId ? prev : currentId));
    };

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        updateActiveFromScroll();
        ticking = false;
      });
    };

    updateActiveFromScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [sections]);

  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    event.preventDefault();
    const el = document.getElementById(id);
    if (!el) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
    setActiveId(id);
  };

  if (!sections.length) return null;

  return (
    <div className="sticky top-14 z-40 -mx-3 sm:-mx-6 px-3 sm:px-6">
      <div className="border-y border-zinc-800/80 bg-zinc-950/95 backdrop-blur-xl">
        <div className="overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          <div className="flex min-w-max items-center gap-1">
            {sections.map((section) => {
              const isActive = activeId === section.id;
              return (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  onClick={(event) => handleClick(event, section.id)}
                  className={`border-b-2 px-4 py-3 text-sm font-semibold tracking-wide whitespace-nowrap transition-colors ${
                    isActive
                      ? "border-blue-500 text-zinc-100"
                      : "border-transparent text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                  }`}
                >
                  {section.label}
                </a>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
