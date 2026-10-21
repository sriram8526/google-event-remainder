"use strict";

// Server text is inserted as plain text nodes only, so it cannot inject markup.
const SWATCHES = ["#1b1f3b", "#0b6e6d", "#f2a900", "#6a4c93", "#c1440e", "#2a7f3f", "#8a6d00", "#4a5068"];
const $ = (id) => document.getElementById(id);

let inflight = null; // AbortController for the current submission

function el(tag, text, attrs = {}) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function append(parent, ...children) {
  children.forEach((child) => parent.appendChild(child));
  return parent;
}

const money = (value, currency) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
const day = (iso) =>
  new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${iso}T00:00:00`));

// One short message per state change. The region exists from page load and is never
// the container that changes, so screen readers are not flooded by re-rendered content.
function announce(message) {
  const region = $("announcer");
  region.textContent = "";
  window.setTimeout(() => { region.textContent = message; }, 50);
}

function readForm() {
  return {
    event_type: $("event_type").value,
    event_date: $("event_date").value,
    guest_count: Number($("guest_count").value),
    budget: $("budget").value,
    currency: $("currency").value,
    location: $("location").value.trim(),
    theme: $("theme").value.trim(),
    venue: $("venue").value,
    interests: $("interests").value.split(",").map((s) => s.trim()).filter(Boolean),
    dietary_needs: [...document.querySelectorAll("#dietary input:checked")].map((c) => c.value),
    needs_accessibility: $("needs_accessibility").checked,
    has_children: $("has_children").checked,
  };
}

function renderBudget(plan) {
  const bar = el("div", undefined, { class: "bar", "aria-hidden": "true" });
  const tbody = el("tbody");
  plan.budget.forEach((line, i) => {
    const color = SWATCHES[i % SWATCHES.length];
    const seg = el("span");
    seg.style.flexGrow = String(line.share_pct);
    seg.style.background = color;
    bar.appendChild(seg);
    const swatch = el("span", undefined, { class: "swatch", "aria-hidden": "true" });
    swatch.style.background = color;
    append(tbody, append(el("tr"),
      append(el("td"), swatch, document.createTextNode(line.label)),
      el("td", money(line.amount, plan.currency), { class: "num" }),
      el("td", `${line.share_pct}%`, { class: "num" })));
  });
  const head = append(el("tr"), el("th", "Category", { scope: "col" }),
    el("th", "Amount", { scope: "col", class: "num" }), el("th", "Share", { scope: "col", class: "num" }));
  const table = append(el("table"),
    el("caption", `Budget split, ${money(plan.per_guest, plan.currency)} per guest`),
    append(el("thead"), head), tbody);
  return append(el("div"), bar, append(el("div", undefined, { class: "scroll" }), table));
}

function renderTimeline(plan) {
  const list = el("ol", undefined, { class: "timeline" });
  plan.timeline.forEach((item) => {
    const li = el("li", `${day(item.due)}: ${item.task}`);
    if (item.urgent) li.appendChild(el("span", "Overdue, do now", { class: "tag" }));
    list.appendChild(li);
  });
  return list;
}

function renderVendors(plan) {
  const grid = el("div", undefined, { class: "vendors" });
  plan.vendors.forEach((vendor, v) => {
    const card = el("div", undefined, { class: "vendor", role: "group", "aria-labelledby": `vendor-${v}` });
    const meta = el("p", `Budget ${money(vendor.budget, plan.currency)}. Book by ${day(vendor.book_by)}.`, { class: "hint" });
    if (vendor.urgent) meta.appendChild(el("span", "Overdue, do now", { class: "tag" }));
    const ul = el("ul");
    vendor.items.forEach((text, i) => {
      const id = `v${v}-i${i}`;
      const label = append(el("label", undefined, { for: id }),
        el("input", undefined, { type: "checkbox", id }), el("span", text));
      append(ul, append(el("li"), label));
    });
    append(card, el("h3", vendor.label, { id: `vendor-${v}` }), meta, ul);
    grid.appendChild(card);
  });
  return grid;
}

function renderIdeas(ideas, notice) {
  const list = el("ul", undefined, { class: "ideas" });
  ideas.forEach((idea) => {
    append(list, append(el("li"), el("strong", idea.title), document.createTextNode(`. ${idea.description}`)));
  });
  return append(el("div"), list, el("p", notice, { class: "hint" }));
}

function render(plan) {
  const out = $("results");
  out.replaceChildren();
  const why = el("ul", undefined, { class: "why" });
  plan.decisions.forEach((d) => why.appendChild(el("li", d)));
  const ideasRegion = el("div", undefined, { id: "ideas-region", "aria-busy": "true" });
  ideasRegion.appendChild(renderIdeas(plan.ideas, "Loading personalised ideas. Built-in ideas are shown meanwhile."));

  append(out, el("h2", "Your plan", { id: "plan-heading" }), el("p", plan.summary));
  plan.warnings.forEach((w) => out.appendChild(el("p", w, { class: "warning" })));
  append(out,
    el("h2", "Why this plan"), why,
    el("h2", "Budget"), renderBudget(plan),
    el("h2", "Timeline"), renderTimeline(plan),
    el("h2", "Vendor checklist"), renderVendors(plan),
    el("h2", "Ideas for your event"), ideasRegion);
  out.hidden = false;
  out.setAttribute("aria-labelledby", "plan-heading");
  out.focus();
}

function showError(message) {
  const box = $("form-error");
  box.textContent = message;
  box.hidden = !message;
}

function describeErrors(body) {
  if (body && Array.isArray(body.errors)) {
    return body.errors.map((e) => `${e.field || "Form"}: ${e.message}`).join(" ");
  }
  return (body && body.detail) || "Something went wrong. Please try again.";
}

async function postJson(url, payload, signal) {
  const response = await fetch(url, {
    method: "POST", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(describeErrors(body));
  return body;
}

async function loadIdeas(payload, signal) {
  const region = $("ideas-region");
  try {
    const result = await postJson("/api/ideas", payload, signal);
    region.replaceChildren(renderIdeas(result.ideas, result.notice));
    announce(result.ai_generated ? "Personalised ideas are ready." : "Built-in ideas are shown.");
  } catch (error) {
    if (error.name === "AbortError") return;
    region.replaceChildren(renderIdeas([], "Personalised ideas could not be loaded. Your plan above is complete."));
  } finally {
    region.setAttribute("aria-busy", "false");
  }
}

async function submit(event) {
  event.preventDefault();
  showError("");
  const form = event.currentTarget;
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  if (inflight) inflight.abort(); // a newer submission supersedes the older one
  inflight = new AbortController();
  const { signal } = inflight;
  const payload = readForm();
  const button = $("submit");
  button.disabled = true;
  button.textContent = "Creating your plan";
  try {
    render(await postJson("/api/plan", payload, signal));
    announce("Your plan is ready. Personalised ideas are loading.");
    button.disabled = false;
    button.textContent = "Create my plan";
    await loadIdeas(payload, signal);
  } catch (error) {
    if (error.name === "AbortError") return;
    showError(error instanceof TypeError ? "Could not reach the server. Check your connection." : error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Create my plan";
  }
}

function init() {
  const today = new Date();
  $("event_date").min = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  $("plan-form").addEventListener("submit", submit);
}

document.addEventListener("DOMContentLoaded", init);
