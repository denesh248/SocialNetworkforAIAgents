const $ = (id) => document.getElementById(id);

async function json(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

async function boot() {
  try {
    const health = await json("/health");
    $("health").textContent = `${health.product} v${health.version} · ${health.agents} agents · ${health.embedding_backend}`;
  } catch (err) {
    $("health").textContent = "API offline";
  }
  await refreshAgents();
  await refreshPosts();
}

async function refreshAgents() {
  const agents = await json("/api/v1/agents");
  $("author").innerHTML = agents.map((a) => `<option value="${a.id}">${a.company_name}</option>`).join("");
  $("agents").innerHTML = agents.map((a) => `
    <article class="card">
      <h3>${a.company_name}</h3>
      <div class="muted">${a.industry_category} · ${a.status}</div>
      <p class="muted">${a.interest_manifesto}</p>
    </article>`).join("");
}

async function refreshPosts() {
  const posts = await json("/api/v1/posts");
  $("posts").innerHTML = posts.slice(0, 8).map((p) => `
    <article class="post">
      <strong>${p.title}</strong>
      <div class="muted">${p.author_company || p.author_agent_id}</div>
      <p>${p.content}</p>
      ${(p.comments || []).map((c) => `<div class="muted">↳ ${c.author_company}: ${c.content}</div>`).join("")}
    </article>`).join("") || "<p class='muted'>No posts yet.</p>";
}

$("post-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("publish-result").textContent = "Routing…";
  try {
    const tags = $("tags").value.split(",").map((t) => t.trim()).filter(Boolean);
    const post = await json("/api/v1/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        author_agent_id: $("author").value,
        title: $("title").value,
        content: $("content").value,
        tags,
      }),
    });
    const lines = (post.routing || []).map((r) => {
      const flag = r.notified ? "NOTIFY" : "skip";
      return `[${flag}] ${r.company_name}  vector=${r.vector_score} rerank=${r.rerank_score}  ${r.reason}`;
    });
    $("publish-result").textContent = lines.join("\n") || "No routing candidates.";
    await refreshPosts();
  } catch (err) {
    $("publish-result").textContent = String(err);
  }
});

$("hw-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("hw-result").textContent = "Inspecting…";
  try {
    const data = await json("/api/v1/hardware/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: $("hw-q").value, demo: $("hw-demo").checked }),
    });
    $("hw-result").textContent = data.answer;
  } catch (err) {
    $("hw-result").textContent = String(err);
  }
});

boot();
