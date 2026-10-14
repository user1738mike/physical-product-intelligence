import type { FormEvent } from "react";

type Props = {
  register: boolean;
  busy: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onToggle: () => void;
};

export default function AuthForm({
  register,
  busy,
  onSubmit,
  onToggle,
}: Props) {
  return (
    <section className="account-panel" aria-labelledby="auth-title">
      <h2 id="auth-title">{register ? "Create an account" : "Sign in"}</h2>
      <p>
        Usernames are case-sensitive. New accounts have no organization access
        until they create or join an organization.
      </p>
      <form onSubmit={onSubmit}>
        <label htmlFor="username">Username</label>
        <input
          id="username"
          name="username"
          autoComplete="username"
          required
          minLength={register ? 3 : 1}
          maxLength={150}
          pattern={register ? "[A-Za-z0-9_.\\-]+" : undefined}
          aria-describedby={register ? "username-help" : undefined}
        />
        {register && (
          <p id="username-help">
            Use letters, numbers, dots, underscores or hyphens.
          </p>
        )}
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete={register ? "new-password" : "current-password"}
          required
          minLength={register ? 12 : 1}
          maxLength={256}
          aria-describedby={register ? "password-help" : undefined}
        />
        {register && (
          <p id="password-help">
            Use at least 12 characters and avoid common passwords or your
            username.
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy
            ? "Please wait…"
            : register
              ? "Create account and sign in"
              : "Sign in"}
        </button>
      </form>
      <button className="text-button" disabled={busy} onClick={onToggle}>
        {register ? "Already have an account? Sign in" : "Create an account"}
      </button>
    </section>
  );
}
