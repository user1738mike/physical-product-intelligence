"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PasswordForm from "../password-form";

export default function Recovery() {
  const [token, setToken] = useState("");
  const [recovered, setRecovered] = useState(false);
  useEffect(() => {
    const candidate =
      new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
    // Fragments are never sent to the server. Remove immediately from history;
    // keep the link only in component memory, never persistent browser storage.
    window.history.replaceState(null, "", window.location.pathname);
    if (/^[a-f0-9]{32}\.[A-Za-z0-9_-]{43}$/.test(candidate))
      setToken(candidate);
  }, []);
  return (
    <main className="account-page">
      <h1>Account recovery</h1>
      {recovered ? (
        <p role="status">
          Password updated. Sign in with your new password. Previous sessions
          and API credentials have been revoked.
        </p>
      ) : token ? (
        <PasswordForm
          token={token}
          onComplete={() => {
            setToken("");
            setRecovered(true);
          }}
        />
      ) : (
        <p>
          If you cannot sign in, contact your service operator through your
          established support channel. After verifying your identity, the
          operator can provide a short-lived recovery link. An organization
          administrator cannot reset another person’s password.
        </p>
      )}
      <Link href="/account">Return to sign in</Link>
    </main>
  );
}
