const form = document.querySelector("#upload-form");
const state = document.querySelector("#state");
const summary = document.querySelector("#summary");
const tbody = document.querySelector("#results tbody");
const download = document.querySelector("#download");

let lastResult = null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = document.querySelector("#file").files[0];
  const limit = document.querySelector("#limit").value;
  if (!file) return;

  state.textContent = "Processing...";
  tbody.innerHTML = "";
  summary.innerHTML = "";
  download.hidden = true;

  const body = new FormData();
  body.append("file", file);
  const includeDelivery = document.querySelector("#include-delivery").checked;
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit);
  if (includeDelivery) params.set("include_delivery", "true");
  const qs = params.toString();
  const url = qs ? `/scrape?${qs}` : "/scrape";

  try {
    const response = await fetch(url, { method: "POST", body });
    if (!response.ok) throw new Error(await response.text());
    lastResult = await response.json();
    render(lastResult);
    state.textContent = "Done.";
  } catch (error) {
    state.textContent = `Failed: ${error.message}`;
  }
});

function render(result) {
  const metrics = result.summary || {};
  summary.innerHTML = Object.entries(metrics)
    .map(([key, value]) => `<div class="metric"><strong>${value}</strong>${escapeHtml(key)}</div>`)
    .join("");

  tbody.innerHTML = (result.products || [])
    .map((product) => {
      const ads = (product.category_ads || []).map((ad) => `${ad.position}. ${ad.title || ""} (${ad.price || ""})`).join("<br>");
      const errors = (product.errors || []).map((err) => `${err.stage}: ${err.code}`).join("<br>");
      const deliveries = (product.delivery_estimates || []).map((d) => `${d.city}: ${d.status}${d.estimated_days ? ` (${d.estimated_days}d)` : ""}`).join("<br>");
      return `<tr>
        <td>${product.row_number || ""}</td>
        <td>${escapeHtml(product.product_id || "")}</td>
        <td><span class="status ${product.status}">${product.status}</span></td>
        <td>${escapeHtml(product.title || "")}</td>
        <td>${product.rating ?? ""}</td>
        <td>${escapeHtml(product.category || "")}</td>
        <td>${ads}</td>
        <td>${deliveries}</td>
        <td>${errors}</td>
      </tr>`;
    })
    .join("");

  const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  download.href = URL.createObjectURL(blob);
  download.download = "myntra-results.json";
  download.hidden = false;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

