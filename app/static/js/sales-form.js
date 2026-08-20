document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector("#sale-items-container");
  const addButton = document.querySelector("#add-sale-line");

  if (!container || !addButton) {
    return;
  }

  const updateIndexes = () => {
    const lineItems = container.querySelectorAll("[data-sale-line]");
    lineItems.forEach((line, index) => {
      line.querySelectorAll("input, select, textarea, label").forEach((element) => {
        ["id", "name", "for"].forEach((attribute) => {
          const currentValue = element.getAttribute(attribute);
          if (!currentValue) {
            return;
          }
          element.setAttribute(attribute, currentValue.replace(/items-\d+-/g, `items-${index}-`));
        });
      });
    });
  };

  const bindRemoveButtons = () => {
    container.querySelectorAll(".remove-sale-line").forEach((button) => {
      button.onclick = () => {
        const lineItems = container.querySelectorAll("[data-sale-line]");
        if (lineItems.length === 1) {
          lineItems[0].querySelectorAll("input").forEach((input) => {
            if (input.type !== "hidden") {
              input.value = "";
            }
          });
          lineItems[0].querySelectorAll("select").forEach((select) => {
            select.selectedIndex = 0;
          });
          return;
        }
        button.closest("[data-sale-line]").remove();
        updateIndexes();
      };
    });
  };

  addButton.addEventListener("click", () => {
    const firstLine = container.querySelector("[data-sale-line]");
    if (!firstLine) {
      return;
    }
    const clone = firstLine.cloneNode(true);
    clone.querySelectorAll("input").forEach((input) => {
      if (input.type !== "hidden") {
        input.value = "";
      }
    });
    clone.querySelectorAll("select").forEach((select) => {
      select.selectedIndex = 0;
    });
    clone.querySelectorAll(".text-danger.small").forEach((errorNode) => errorNode.remove());
    container.appendChild(clone);
    updateIndexes();
    bindRemoveButtons();
  });

  bindRemoveButtons();
});
