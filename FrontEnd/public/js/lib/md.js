// Minimal, safe Markdown -> HTML for agent output (bold, italic, code, lists).
// Escapes all HTML first, so no untrusted markup can execute.
export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

export function renderMarkdown(src) {
  const lines = String(src || "").replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let list = null; // 'ul' | 'ol'
  let inCode = false, code = [];

  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) { out.push("<pre><code>" + escapeHtml(code.join("\n")) + "</code></pre>"); code = []; inCode = false; }
      else { closeList(); inCode = true; }
      continue;
    }
    if (inCode) { code.push(line); continue; }

    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ul) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push("<li>" + inline(ul[1]) + "</li>");
    } else if (ol) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push("<li>" + inline(ol[1]) + "</li>");
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList();
      out.push("<p>" + inline(line) + "</p>");
    }
  }
  if (inCode) out.push("<pre><code>" + escapeHtml(code.join("\n")) + "</code></pre>");
  closeList();
  return out.join("");
}
