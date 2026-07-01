// Header muda de estilo ao rolar a página
const header = document.querySelector("header");
window.addEventListener("scroll", () => {
  header.classList.toggle("scrolled", window.scrollY > 40);
});

// Menu mobile
const menuToggle = document.querySelector(".menu-toggle");
const nav = document.querySelector("nav");

menuToggle?.addEventListener("click", () => {
  nav.classList.toggle("open");
});

document.querySelectorAll(".nav-links a").forEach((link) => {
  link.addEventListener("click", () => nav.classList.remove("open"));
});

// Animação de entrada ao rolar (Intersection Observer)
const revealEls = document.querySelectorAll(".reveal");
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.15 }
);

revealEls.forEach((el) => observer.observe(el));

// Ano atual no rodapé
const anoEl = document.getElementById("ano-atual");
if (anoEl) anoEl.textContent = new Date().getFullYear();
