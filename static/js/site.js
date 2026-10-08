document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }
  document.querySelectorAll(".flash").forEach((message) => {
    window.setTimeout(() => message.remove(), 5500);
  });
  document.querySelectorAll(".faq-question").forEach((question) => {
    question.addEventListener("click", () => {
      const answer = question.nextElementSibling;
      const isOpen = !answer.hidden;
      answer.hidden = isOpen;
      question.setAttribute("aria-expanded", String(!isOpen));
    });
  });
});