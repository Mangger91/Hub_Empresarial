(function () {
    function applySidebarState(collapsed) {
        document.documentElement.classList.toggle("sidebar-is-collapsed", collapsed);
        const button = document.querySelector("[data-sidebar-toggle]");
        if (!button) return;
        button.setAttribute("aria-label", collapsed ? "Expandir menu lateral" : "Ocultar menu lateral");
        button.setAttribute("title", collapsed ? "Expandir menu lateral" : "Ocultar menu lateral");
    }

    function applyTheme(theme) {
        const dark = theme === "dark";
        document.documentElement.dataset.theme = dark ? "dark" : "light";
        const button = document.querySelector("[data-theme-toggle]");
        if (!button) return;
        button.setAttribute("aria-pressed", String(dark));
        button.setAttribute("title", dark ? "Usar modo claro" : "Usar modo dark");
        const label = button.querySelector("[data-theme-label]");
        if (label) label.textContent = dark ? "Modo claro" : "Modo dark";
    }

    const storedTheme = localStorage.getItem("theme") || "light";
    applyTheme(storedTheme);

    document.addEventListener("DOMContentLoaded", function () {
        const collapsed = localStorage.getItem("sidebar-collapsed") === "true";
        applySidebarState(collapsed);

        const button = document.querySelector("[data-sidebar-toggle]");
        if (button) button.addEventListener("click", function () {
            const nextState = !document.documentElement.classList.contains("sidebar-is-collapsed");
            localStorage.setItem("sidebar-collapsed", String(nextState));
            applySidebarState(nextState);
        });

        applyTheme(localStorage.getItem("theme") || "light");
        const themeButton = document.querySelector("[data-theme-toggle]");
        if (themeButton) themeButton.addEventListener("click", function () {
            const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
            localStorage.setItem("theme", nextTheme);
            applyTheme(nextTheme);
        });

        document.querySelectorAll("[data-stock-modal-open]").forEach(function (trigger) {
            trigger.addEventListener("click", function () {
                const modal = document.getElementById(trigger.dataset.stockModalOpen);
                if (!modal) return;
                if (typeof modal.showModal === "function") {
                    modal.showModal();
                } else {
                    modal.setAttribute("open", "");
                }
            });
        });

        document.querySelectorAll(".stock-modal").forEach(function (modal) {
            modal.querySelectorAll("[data-stock-modal-close]").forEach(function (button) {
                button.addEventListener("click", function () {
                    modal.close();
                });
            });

            modal.addEventListener("click", function (event) {
                if (event.target === modal) {
                    modal.close();
                }
            });
        });
    });
})();
