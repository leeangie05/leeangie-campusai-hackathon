"use client";

import { FormEvent, useState } from "react";
import { supabase } from "@/lib/supabase";

export default function AuthPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAuth = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({
          email,
          password,
        });

        if (error) throw error;
        setMessage("Account created. Now sign in.");
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (error) throw error;
        setMessage("Signed in successfully.");
        const { data: userData, error: userError } = await supabase.auth.getUser();

        if (userError || !userData.user) {
        throw new Error("Could not get signed-in user.");
        }

        const user = userData.user;

        const { data: profile, error: profileError } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", user.id)
        .single();

        if (profileError && profileError.code !== "PGRST116") {
        throw profileError;
        }

        if (!profile) {
        const { error: insertError } = await supabase.from("profiles").insert([
            {
            id: user.id,
            email: user.email,
            },
        ]);

        if (insertError) throw insertError;

        window.location.href = "/onboarding";
        } else {
        window.location.href = "/dashboard";
        }
      }
    } catch (err: any) {
      setMessage(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f8fb] px-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Welcome to Syllabot</h1>
          <p className="mt-2 text-slate-600">
            Sign in to build and save your study plan.
          </p>
        </div>

        <div className="mb-6 flex rounded-2xl bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setMode("signup")}
            className={`flex-1 rounded-xl px-4 py-2 text-sm font-medium ${
              mode === "signup"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500"
            }`}
          >
            Sign Up
          </button>
          <button
            type="button"
            onClick={() => setMode("signin")}
            className={`flex-1 rounded-xl px-4 py-2 text-sm font-medium ${
              mode === "signin"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500"
            }`}
          >
            Sign In
          </button>
        </div>

        <form onSubmit={handleAuth} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              type="email"
              placeholder="you@school.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              type="password"
              placeholder="Enter a password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-2xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            {loading
              ? "Loading..."
              : mode === "signup"
              ? "Create Account"
              : "Sign In"}
          </button>
        </form>

        {message && (
          <p className="mt-4 text-sm text-slate-600">{message}</p>
        )}
      </div>
    </main>
  );
}