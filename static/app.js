document.documentElement.classList.add("js");

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.7 } });
}

function markInvalidFields(root) {
  root.querySelectorAll(".field-errors").forEach((container) => {
    if (!container.textContent.trim()) return;
    root.querySelectorAll(`[aria-describedby~="${container.id}"]`).forEach((input) => input.setAttribute("aria-invalid", "true"));
    const details = container.closest("details");
    if (details) details.open = true;
  });
}

function addPartRow(button) {
  const total = document.getElementById("id_parts-TOTAL_FORMS");
  const max = Number(document.getElementById("id_parts-MAX_NUM_FORMS").value);
  const index = Number(total.value);
  if (index >= max) return;
  const html = document.getElementById("part-template").innerHTML.replaceAll("__prefix__", String(index));
  document.getElementById("parts-list").insertAdjacentHTML("beforeend", html);
  total.value = String(index + 1);
  refreshIcons();
  document.getElementById(`id_parts-${index}-name`).focus();
  if (index + 1 >= max) button.hidden = true;
}

document.addEventListener("DOMContentLoaded", () => {
  refreshIcons();
  markInvalidFields(document);
  const invalidField = document.querySelector('[aria-invalid="true"]');
  if (invalidField) invalidField.focus();

  document.querySelectorAll("[data-autosubmit]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.type === "file" && !input.files.length) return;
      const label = input.closest(".upload-button");
      if (label) label.classList.add("is-busy");
      input.form.requestSubmit();
    });
  });
  document.querySelectorAll("[data-add-part]").forEach((button) => button.addEventListener("click", () => addPartRow(button)));
  document.querySelectorAll(".column-chart").forEach((chart) => { chart.scrollLeft = chart.scrollWidth; });
});

document.addEventListener("submit", (event) => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
document.addEventListener("htmx:afterSwap", (event) => {
  refreshIcons();
  markInvalidFields(event.target);
});