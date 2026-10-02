/** Cloudflare-hosted static website and API gateway to the actual agent engine. */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const security = { "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY", "X-Pairlit-Hosting": "cloudflare-worker" };
    const json = (message, status) => new Response(JSON.stringify({detail: message}), {status, headers: {...security, "Content-Type": "application/json"}});
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") {
      if (!["GET", "HEAD", "POST"].includes(request.method)) return json("Method not allowed", 405);
      if (request.method === "POST" && request.headers.get("X-Pairlit-Client") !== "web") return json("Pairlit client header required", 403);
      let origin;
      try { origin = new URL(env.PAIRLIT_API_ORIGIN); } catch { return json("Agent engine origin is not configured", 503); }
      if (origin.protocol !== "https:" || origin.username || origin.password) return json("Invalid agent engine origin", 503);
      const upstream = new URL(url.pathname + url.search, origin);
      const headers = new Headers();
      for (const key of ["Content-Type", "X-Pairlit-Client", "Accept"]) {
        const value = request.headers.get(key);
        if (value) headers.set(key, value);
      }
      let body;
      if (request.method === "POST") {
        body = await request.arrayBuffer();
        if (body.byteLength > 10000) return json("Request too large", 413);
      }
      try {
        const response = await fetch(upstream, {method: request.method, headers, body, redirect: "manual"});
        const out = new Headers(response.headers);
        for (const [key, value] of Object.entries(security)) out.set(key, value);
        out.set("Cache-Control", "no-store");
        out.delete("Set-Cookie");
        return new Response(response.body, {status: response.status, headers: out});
      } catch {
        return json("Agent engine is temporarily unavailable. Keep the configured engine and model running.", 503);
      }
    }
    const response = await env.ASSETS.fetch(request);
    const headers = new Headers(response.headers);
    for (const [key, value] of Object.entries(security)) headers.set(key, value);
    return new Response(response.body, {status: response.status, headers});
  }
};
