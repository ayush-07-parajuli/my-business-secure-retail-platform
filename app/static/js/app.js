document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      document.body.classList.toggle("app-shell-open");
    });
  });

  if (!window.bootstrap) {
    return;
  }

  window.setTimeout(() => {
    document.querySelectorAll(".alert").forEach((alertElement) => {
      if (alertElement.classList.contains("show")) {
        const alertInstance = bootstrap.Alert.getOrCreateInstance(alertElement);
        alertInstance.close();
      }
    });
  }, 4500);
});
