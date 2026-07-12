const form = document.querySelector("#upload-form");
const state = document.querySelector("#state");
const summary = document.querySelector("#summary");
const tbody = document.querySelector("#results tbody");
const download = document.querySelector("#download");
const emptyState = document.querySelector("#empty-state");
const submitButton = document.querySelector("#run-btn");

let lastResult = null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = document.querySelector("#file").files[0];
  const limit = document.querySelector("#limit").value;
  if (!file) return;

  setProcessing(true);
  setState("Processing CSV and fetching product data\u2026", "processing");
  tbody.innerHTML = "";
  summary.innerHTML = "";
  download.hidden = true;
  emptyState.classList.add("hidden");

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
    setState("Done.", "success");
  } catch (error) {
    setState(`Failed: ${error.message}`, "failed");
  } finally {
    setProcessing(false);
  }
});

function render(result) {
  const metrics = result.summary || {};
  summary.innerHTML = Object.entries(metrics)
    .map(([key, value]) => `<div class="metric"><strong>${value}</strong>${escapeHtml(key)}</div>`)
    .join("");

  const products = result.products || [];
  if (products.length) {
    emptyState.classList.add("hidden");
  }

  tbody.innerHTML = products
    .map((product) => {
      const ads = renderLines(product.category_ads || [], (ad) => `${ad.position}. ${ad.title || "Untitled"}${ad.price ? ` \u2014 ${ad.price}` : ""}`);
      const errors = renderLines(product.errors || [], (err) => `${err.stage}: ${err.code}`, "error-line", "No errors");
      const deliveries = renderLines(
        product.delivery_estimates || [],
        (d) => `${d.city}: ${d.status}${d.estimated_days ? ` (${d.estimated_days}d)` : ""}`,
        "delivery-line",
        "Not requested",
      );
      const images = renderImages(product.images || [], product.title);
      return `<tr>
        <td>${product.row_number || ""}</td>
        <td>${escapeHtml(product.product_id || "")}</td>
        <td><span class="status ${product.status}">${product.status}</span></td>
        <td>${images}</td>
        <td>${escapeHtml(product.title || "")}</td>
        <td>${product.rating ?? ""}</td>
        <td>${escapeHtml(product.category || "")}</td>
        <td>${ads}</td>
        <td>${deliveries}</td>
        <td>${errors}</td>
      </tr>`;
    })
    .join("");
  bindImageFallbacks();

  const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  download.href = URL.createObjectURL(blob);
  download.download = "myntra-results.json";
  download.hidden = false;
}

function setProcessing(isProcessing) {
  submitButton.disabled = isProcessing;
  submitButton.textContent = isProcessing ? "Running\u2026" : "Run";
}

function setState(message, type) {
  state.className = `state ${type || ""}`.trim();
  state.textContent = message;
}

function renderLines(items, formatter, className = "", emptyText = "None") {
  if (!items.length) return `<span class="muted">${escapeHtml(emptyText)}</span>`;
  const classes = ["pill-line", className].filter(Boolean).join(" ");
  return `<div class="stack">${items.map((item) => `<span class="${classes}">${escapeHtml(formatter(item))}</span>`)}</div>`;
}

function renderImages(images, title) {
  const imageUrl = images.find((url) => typeof url === "string" && url.startsWith("https://"));
  if (!imageUrl) return `<span class="muted">No image</span>`;
  const alt = title ? `${title} product image` : "Product image";
  return `<a class="image-link" href="${escapeAttribute(imageUrl)}" target="_blank" rel="noopener noreferrer">
    <img class="product-thumb" src="${escapeAttribute(imageUrl)}" alt="${escapeAttribute(alt)}" width="72" height="82" loading="lazy" />
  </a>`;
}

function bindImageFallbacks() {
  tbody.querySelectorAll(".product-thumb").forEach((image) => {
    image.addEventListener("error", () => {
      const fallback = document.createElement("span");
      fallback.className = "muted";
      fallback.textContent = "No image";
      image.closest(".image-link").replaceWith(fallback);
    }, { once: true });
  });
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

function escapeAttribute(value) {
  return escapeHtml(value);
}
