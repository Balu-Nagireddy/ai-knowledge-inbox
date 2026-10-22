const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.error("Health check error:", err);
    return { status: "offline", error: err.message };
  }
}

export async function fetchItems() {
  const res = await fetch(`${API_BASE}/items`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to fetch items");
  }
  return await res.json();
}

export async function ingestItem({ sourceType, content, url, title }) {
  const payload = {
    source_type: sourceType,
    title: title ? title.trim() : undefined,
    content: sourceType === "note" ? content.trim() : undefined,
    url: sourceType === "url" ? url.trim() : undefined,
  };

  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to ingest item");
  }

  return await res.json();
}

export async function uploadFileItem({ file, title }) {
  const formData = new FormData();
  formData.append("file", file);
  if (title && title.trim()) {
    formData.append("title", title.trim());
  }

  const res = await fetch(`${API_BASE}/ingest/file`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to upload and ingest file");
  }

  return await res.json();
}

export async function searchWebAndAnswer(question) {
  const res = await fetch(`${API_BASE}/query/web-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question.trim() }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Web search query failed");
  }

  return await res.json();
}

export async function deleteItem(id) {
  const res = await fetch(`${API_BASE}/items/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to delete item");
  }
  return await res.json();
}

export async function queryKnowledge(question, topK = 4) {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question.trim(), top_k: topK }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to query knowledge");
  }

  return await res.json();
}

export async function queryKnowledgeStream(question, topK = 4, { onSources, onToken, onDone, onError }) {
  try {
    const response = await fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question.trim(), top_k: topK }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || "Streaming query failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;
        const lines = block.split("\n");
        let eventType = "message";
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.replace("event: ", "").trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.replace("data: ", "").trim();
          }
        }

        if (eventType === "sources") {
          try {
            const sources = JSON.parse(dataStr);
            if (onSources) onSources(sources);
          } catch (e) {
            console.error("Failed to parse sources event:", e);
          }
        } else if (eventType === "token") {
          try {
            const token = JSON.parse(dataStr);
            if (onToken) onToken(token);
          } catch {
            if (onToken) onToken(dataStr);
          }
        } else if (eventType === "done") {
          if (onDone) onDone();
        }
      }
    }

    if (onDone) onDone();
  } catch (err) {
    if (onError) onError(err);
    else throw err;
  }
}
