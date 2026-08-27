(function () {
    function applySidebarState(collapsed) {
        document.documentElement.classList.toggle("sidebar-is-collapsed", collapsed);
        const button = document.querySelector("[data-sidebar-toggle]");
        if (!button) return;
        button.setAttribute("aria-label", collapsed ? "Expandir menu lateral" : "Ocultar menu lateral");
        button.setAttribute("title", collapsed ? "Expandir menu lateral" : "Ocultar menu lateral");
    }

    document.addEventListener("DOMContentLoaded", function () {
        const collapsed = localStorage.getItem("sidebar-collapsed") === "true";
        applySidebarState(collapsed);

        const button = document.querySelector("[data-sidebar-toggle]");
        if (!button) return;

        button.addEventListener("click", function () {
            const nextState = !document.documentElement.classList.contains("sidebar-is-collapsed");
            localStorage.setItem("sidebar-collapsed", String(nextState));
            applySidebarState(nextState);
        });
    });
})();
