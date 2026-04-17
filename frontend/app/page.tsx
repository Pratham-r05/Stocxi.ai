// Landing page — storytelling layout

import LandingNavbar from "@/components/home/LandingNavbar";
import HeroSection from "@/components/home/HeroSection";
import ProblemSection from "@/components/home/ProblemSection";
import SolutionSection from "@/components/home/SolutionSection";
import HowItWorksSection from "@/components/home/HowItWorksSection";
import PricingSection from "@/components/home/PricingSection";
import LandingFooter from "@/components/home/LandingFooter";
import MarketTickerBar from "@/components/home/MarketTickerBar";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-black text-white pb-24">
      <LandingNavbar />
      <HeroSection />
      <ProblemSection />
      <SolutionSection />
      <HowItWorksSection />
      <PricingSection />
      <LandingFooter />
      <MarketTickerBar />
    </div>
  );
}
