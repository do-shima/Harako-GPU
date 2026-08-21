(() => {
  "use strict";
  const note = document.querySelector("[data-evidence-note]");
  if (!note) return;
  const language = document.documentElement.lang.startsWith("ja") ? "ja" : "en";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "evidence-toggle";
  button.textContent = language === "ja" ? "検証範囲を確認する" : "Review validation limits";
  button.setAttribute("aria-expanded", "false");
  button.addEventListener("click", () => {
    const visible = note.hasAttribute("hidden");
    note.toggleAttribute("hidden", !visible);
    button.setAttribute("aria-expanded", String(visible));
    if (visible) note.focus();
  });
  document.body.append(button);
})();
