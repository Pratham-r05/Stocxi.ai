"use client";

// Login page — Sign In / Create Account with email+password or Google OAuth

import { signIn, useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Eye, EyeOff } from "lucide-react";

/* ──────────────────────────── helpers ──────────────────────────── */

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
    <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
    <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
    <path fill="#FBBC05" d="M3.964 10.706c-.18-.54-.282-1.117-.282-1.706s.102-1.166.282-1.706V4.962H.957C.347 6.175 0 7.55 0 9s.348 2.825.957 4.038l3.007-2.332z"/>
    <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.962L3.964 6.294C4.672 4.169 6.656 3.58 9 3.58z"/>
  </svg>
);

function PasswordInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? "Password"}
        className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500 pr-10"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  );
}

function Divider() {
  return (
    <div className="flex items-center gap-3 my-5">
      <div className="flex-1 h-px bg-zinc-800" />
      <span className="text-xs text-zinc-600">or</span>
      <div className="flex-1 h-px bg-zinc-800" />
    </div>
  );
}

/* ──────────────────────────── Sign In tab ──────────────────────────── */

function SignInTab({ onSwitchToCreate }: { onSwitchToCreate: (prefillEmail?: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCredentials(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError(null);

    const res = await signIn("credentials", {
      email: email.trim(),
      password,
      redirect: false,
    });

    setLoading(false);
    if (res?.error) {
      setError("Incorrect email or password. Please try again.");
    } else {
      window.location.href = "/";
    }
  }

  async function handleGoogle() {
    setGoogleLoading(true);
    setError(null);
    try {
      await signIn("google", { callbackUrl: "/" });
    } catch {
      setError("Google sign-in failed. Please try again.");
      setGoogleLoading(false);
    }
  }

  return (
    <form onSubmit={handleCredentials} className="flex flex-col gap-3">
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <p className="text-xs text-red-400 leading-relaxed">{error}</p>
        </div>
      )}

      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email address"
        required
        className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
      />
      <PasswordInput value={password} onChange={setPassword} />

      <button
        type="submit"
        disabled={loading || !email || !password}
        className="w-full py-3 rounded-xl bg-white text-zinc-950 text-sm font-semibold hover:bg-zinc-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-1"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-zinc-400 border-t-zinc-900 animate-spin" />
            Signing in…
          </span>
        ) : (
          "Sign In"
        )}
      </button>

      <Divider />

      <button
        type="button"
        onClick={handleGoogle}
        disabled={googleLoading}
        className="w-full flex items-center justify-center gap-3 border border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-xl px-4 py-3 transition-colors"
      >
        {googleLoading ? (
          <span className="w-4 h-4 rounded-full border-2 border-zinc-500 border-t-white animate-spin" />
        ) : (
          <GoogleIcon />
        )}
        Continue with Google
      </button>

      <p className="text-center text-xs text-zinc-600 mt-2">
        Don&apos;t have an account?{" "}
        <button
          type="button"
          onClick={() => onSwitchToCreate()}
          className="text-zinc-400 hover:text-white transition-colors underline underline-offset-2"
        >
          Create one
        </button>
      </p>
    </form>
  );
}

/* ──────────────────────────── Create Account tab ──────────────────────────── */

function CreateAccountTab({
  onCreated,
  onSwitchToSignIn,
}: {
  onCreated: (email: string) => void;
  onSwitchToSignIn: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !password) return;
    setLoading(true);
    setError(null);

    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), email: email.trim(), password }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      setError(data.error ?? "Something went wrong. Please try again.");
      return;
    }

    onCreated(email.trim());
  }

  async function handleGoogle() {
    setGoogleLoading(true);
    setError(null);
    try {
      await signIn("google", { callbackUrl: "/" });
    } catch {
      setError("Google sign-in failed. Please try again.");
      setGoogleLoading(false);
    }
  }

  return (
    <form onSubmit={handleCreate} className="flex flex-col gap-3">
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <p className="text-xs text-red-400 leading-relaxed">{error}</p>
        </div>
      )}

      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Full name"
        required
        className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
      />
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email address"
        required
        className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
      />
      <PasswordInput value={password} onChange={setPassword} placeholder="Password (min 6 chars)" />

      <button
        type="submit"
        disabled={loading || !name || !email || !password}
        className="w-full py-3 rounded-xl bg-white text-zinc-950 text-sm font-semibold hover:bg-zinc-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-1"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-zinc-400 border-t-zinc-900 animate-spin" />
            Creating account…
          </span>
        ) : (
          "Create Account"
        )}
      </button>

      <Divider />

      <button
        type="button"
        onClick={handleGoogle}
        disabled={googleLoading}
        className="w-full flex items-center justify-center gap-3 border border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-xl px-4 py-3 transition-colors"
      >
        {googleLoading ? (
          <span className="w-4 h-4 rounded-full border-2 border-zinc-500 border-t-white animate-spin" />
        ) : (
          <GoogleIcon />
        )}
        Continue with Google
      </button>

      <p className="text-center text-xs text-zinc-600 mt-2">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onSwitchToSignIn}
          className="text-zinc-400 hover:text-white transition-colors underline underline-offset-2"
        >
          Sign in
        </button>
      </p>
    </form>
  );
}

/* ──────────────────────────── Main ──────────────────────────── */

type Tab = "signin" | "create";

function LoginContent() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<Tab>("signin");
  const [prefillEmail, setPrefillEmail] = useState("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  useEffect(() => {
    const err = searchParams.get("error");
    if (err === "OAuthSignin" || err === "OAuthCallback") {
      setUrlError("Google sign-in failed. Check your OAuth credentials in .env.local.");
    } else if (err === "Configuration") {
      setUrlError("Auth not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.local.");
    } else if (err) {
      setUrlError(`Sign-in error: ${err}`);
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

  function handleCreated(email: string) {
    setPrefillEmail(email);
    setTab("signin");
    setSuccessMsg("Account created! Sign in with your email and password.");
  }

  function switchToCreate(email?: string) {
    setPrefillEmail(email ?? "");
    setSuccessMsg(null);
    setTab("create");
  }

  return (
    <div className="min-h-screen bg-[#000000] flex flex-col items-center justify-center px-4 relative overflow-hidden">
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
          {/* URL error (OAuth failures) */}
          {urlError && (
            <div className="mb-5 flex items-start gap-2.5 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-xs text-red-400 leading-relaxed">{urlError}</p>
            </div>
          )}

          {/* Success message after account creation */}
          {successMsg && (
            <div className="mb-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3">
              <p className="text-xs text-emerald-400 leading-relaxed">{successMsg}</p>
            </div>
          )}

          {/* Tabs */}
          <div className="flex rounded-xl bg-zinc-800 p-1 mb-6">
            {(["signin", "create"] as Tab[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => { setTab(t); setSuccessMsg(null); }}
                className={`flex-1 text-sm font-medium py-2 rounded-lg transition-colors ${
                  tab === t
                    ? "bg-zinc-700 text-white"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {t === "signin" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          {tab === "signin" ? (
            <SignInTab key={prefillEmail} onSwitchToCreate={switchToCreate} />
          ) : (
            <CreateAccountTab onCreated={handleCreated} onSwitchToSignIn={() => setTab("signin")} />
          )}
        </div>

        <p className="mt-6 text-center text-xs text-zinc-700">
          By continuing, you agree to our Terms of Service
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
