"use client";

// Login page — Google OAuth sign-in

import { signIn, useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";

function LoginContent() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check for NextAuth error in URL (e.g. ?error=OAuthSignin)
  useEffect(() => {
    const urlError = searchParams.get("error");
    if (urlError === "OAuthSignin" || urlError === "OAuthCallback") {
      setError("Google sign-in failed. Make sure your Google OAuth credentials are configured correctly.");
    } else if (urlError === "Configuration") {
      setError("Auth is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env.local file.");
    } else if (urlError) {
      setError(`Sign-in error: ${urlError}`);
    }
  }, [searchParams]);

  useEffect(() => {
    if (session) router.replace("/");
  }, [session, router]);

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-800 border-t-white animate-spin" />
      </div>
    );
  }

  async function handleGoogleSignIn() {
    setIsLoading(true);
    setError(null);
    try {
      await signIn("google", { callbackUrl: "/" });
    } catch {
      setError("Something went wrong. Please try again.");
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#000000] flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Hero glow */}
      <div className="hero-glow absolute inset-x-0 top-0 h-80" />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative z-10 w-full max-w-sm"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <span className="text-3xl font-black tracking-tighter text-white">Stocxi</span>
          <p className="text-zinc-600 text-xs mt-1">AI Stock Analysis</p>
        </div>

        {/* Card */}
        <div className="border border-zinc-800 bg-zinc-900 rounded-2xl p-8">
          <h1 className="text-xl font-bold text-white text-center mb-1">
            Welcome back
          </h1>
          <p className="text-zinc-500 text-sm text-center mb-8">
            Sign in to access AI stock analysis
          </p>

          {/* Error message */}
          {error && (
            <div className="mb-5 flex items-start gap-2.5 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-xs text-red-400 leading-relaxed">{error}</p>
            </div>
          )}

          {/* Google button */}
          <button
            onClick={handleGoogleSignIn}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 bg-white hover:bg-zinc-100 disabled:opacity-60 disabled:cursor-not-allowed text-zinc-900 font-semibold text-sm rounded-xl px-4 py-3 transition-colors"
          >
            {isLoading ? (
              <div className="w-4 h-4 rounded-full border-2 border-zinc-400 border-t-zinc-900 animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
                <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
                <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                <path fill="#FBBC05" d="M3.964 10.706c-.18-.54-.282-1.117-.282-1.706s.102-1.166.282-1.706V4.962H.957C.347 6.175 0 7.55 0 9s.348 2.825.957 4.038l3.007-2.332z"/>
                <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.962L3.964 6.294C4.672 4.169 6.656 3.58 9 3.58z"/>
              </svg>
            )}
            {isLoading ? "Signing in…" : "Continue with Google"}
          </button>

          <p className="mt-6 text-center text-xs text-zinc-700">
            By signing in, you agree to our Terms of Service
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-zinc-700">
          AI-powered stock analysis for Indian markets
        </p>
      </motion.div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[#000000] flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-800 border-t-white animate-spin" />
      </div>
    }>
      <LoginContent />
    </Suspense>
  );
}
