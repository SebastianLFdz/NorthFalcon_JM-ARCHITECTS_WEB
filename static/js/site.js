document.addEventListener("DOMContentLoaded", () => {
  // Menú móvil
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.getElementById("main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  // Menú del usuario: se cierra al hacer clic fuera
  const menuUsuario = document.querySelector(".nav-usuario details");
  if (menuUsuario) {
    document.addEventListener("click", (e) => {
      if (!menuUsuario.contains(e.target)) menuUsuario.removeAttribute("open");
    });
  }

  // Mensajes temporales
  document.querySelectorAll(".flash").forEach((message) => {
    window.setTimeout(() => message.remove(), 6000);
  });

  // Preguntas frecuentes
  document.querySelectorAll(".faq-question").forEach((question) => {
    question.addEventListener("click", () => {
      const answer = question.nextElementSibling;
      const open = answer.classList.toggle("show");
      question.setAttribute("aria-expanded", String(open));
    });
  });

  // Slider de las notas del blog
  const slides = document.querySelectorAll(".slide");
  if (slides.length) {
    let actual = 0;
    const mostrar = (i) => {
      actual = (i + slides.length) % slides.length;
      slides.forEach((s, n) => { s.style.display = n === actual ? "block" : "none"; });
    };
    mostrar(0);
    if (slides.length > 1) window.setInterval(() => mostrar(actual + 1), 3000);
  }

  // Ventanas de diálogo (editar proyecto, mensaje enviado)
  document.querySelectorAll("[data-abrir]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const dialogo = document.getElementById(boton.dataset.abrir);
      if (dialogo) dialogo.showModal();
    });
  });
  document.querySelectorAll("dialog").forEach((dialogo) => {
    dialogo.querySelectorAll("[data-cerrar]").forEach((b) => b.addEventListener("click", () => dialogo.close()));
    dialogo.addEventListener("click", (e) => { if (e.target === dialogo) dialogo.close(); });
  });

  // Archivos: reducir fotos grandes y validar tamaño (Vercel admite máximo 4.5 MB por petición)
  document.querySelectorAll('input[type="file"]').forEach((input) => {
    input.addEventListener("change", async () => {
      let archivo = input.files[0];
      if (!archivo) return;
      if (input.hasAttribute("data-comprimir")) {
        try {
          const reducido = await reducirImagen(archivo);
          if (reducido !== archivo) {
            const dt = new DataTransfer();
            dt.items.add(reducido);
            input.files = dt.files;
            archivo = reducido;
          }
        } catch (e) {
          // Si el navegador no puede procesar la imagen se envía la original.
        }
      }
      const maxMb = parseFloat(input.dataset.maxMb || "4");
      if (archivo.size > maxMb * 1024 * 1024) {
        alert(`El archivo pesa ${(archivo.size / 1048576).toFixed(1)} MB. El máximo permitido es ${maxMb} MB.`);
        input.value = "";
      }
    });
  });
});

async function reducirImagen(archivo, ladoMaximo = 1920, calidad = 0.85) {
  if (!/^image\/(jpeg|png|webp)$/.test(archivo.type)) return archivo;
  const bitmap = await createImageBitmap(archivo);
  const escala = Math.min(1, ladoMaximo / Math.max(bitmap.width, bitmap.height));
  if (escala === 1 && archivo.size <= 1.5 * 1024 * 1024) return archivo;

  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * escala);
  canvas.height = Math.round(bitmap.height * escala);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff"; // fondo blanco para PNG con transparencia
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", calidad));
  if (!blob || blob.size >= archivo.size) return archivo;
  return new File([blob], archivo.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
}
