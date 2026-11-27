(() => {
  "use strict";

  const toggle = document.querySelector(".nav-toggle");
  const nav = document.getElementById("primary-nav");
  if (!toggle || !nav) return;

  const mobile = window.matchMedia("(max-width: 760px)");
  function syncNavigation() {
    toggle.hidden = !mobile.matches;
    if (!mobile.matches) {
      toggle.setAttribute("aria-expanded", "false");
      nav.hidden = false;
    } else {
      nav.hidden = toggle.getAttribute("aria-expanded") !== "true";
    }
  }

  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    nav.hidden = expanded;
  });
  mobile.addEventListener("change", syncNavigation);
  syncNavigation();
})();
