"use client";

import { useState } from "react";
import { ApiError, request } from "../../lib/api";

export default function PasswordForm({
  token,
  onComplete,
}: {
  token?: string;
  onComplete?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const password = String(values.get("new-password"));
    const confirm = String(values.get("confirm-password"));
    const current = String(values.get("current-password") ?? "");
    form.reset();
    if (password !== confirm) {
      setMessage("The new passwords must match. Please enter them again.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await request<void>(
        token ? "/api/v1/auth/recover/" : "/api/v1/auth/password/",
        "POST",
        token
          ? { token, new_password: password }
          : { current_password: current, new_password: password },
      );
      setDone(true);
      setMessage(
        "Password updated. Sign in with your new password. Previous sessions and API credentials have been revoked.",
      );
      onComplete?.();
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Connection failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-panel" aria-labelledby="password-title">
      <h2 id="password-title">
        {token ? "Recover your account" : "Change password"}
      </h2>
      <p>
        Use at least 12 characters. Updating your password signs out every
        session and revokes API credentials you issued.
      </p>
      <p role="status" aria-live="polite">
        {message}
      </p>
      {!done && (
        <form onSubmit={submit}>
          {!token && (
            <>
              <label htmlFor="current-password">Current password</label>
              <input
                id="current-password"
                name="current-password"
                type="password"
                autoComplete="current-password"
                required
                maxLength={256}
              />
            </>
          )}
          <label htmlFor="new-password">New password</label>
          <input
            id="new-password"
            name="new-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
          />
          <label htmlFor="confirm-password">Confirm new password</label>
          <input
            id="confirm-password"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Updating…" : "Update password"}
          </button>
        </form>
      )}
    </section>
  );
}
