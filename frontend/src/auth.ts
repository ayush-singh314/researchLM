import { createAuthClient } from "@neondatabase/neon-js/auth";

const authUrl = import.meta.env.VITE_NEON_AUTH_URL;
if (!authUrl) {
  throw new Error("VITE_NEON_AUTH_URL is not set");
}

export const authClient = createAuthClient(authUrl);

export async function getAccessToken(): Promise<string | null> {
  const result = await authClient.getSession();
  return result.data?.session?.token ?? null;
}
