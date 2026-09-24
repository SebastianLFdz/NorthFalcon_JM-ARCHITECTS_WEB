const slides = document.querySelectorAll(".slide");
let currentSlide = 0;

function showSlide(slideIndex) {
    if (slideIndex < 0) {
        currentSlide = slides.length - 1;
    } else if (slideIndex >= slides.length) {
        currentSlide = 0; // 
    } else {
        currentSlide = slideIndex; 
    }

    slides.forEach((slide) => (slide.style.display = "none"));
    slides[currentSlide].style.display = "block";
}

showSlide(currentSlide);

setInterval(() => {
    showSlide(currentSlide + 1);
}, 3000); // Cambia las imágenes cada 3 segundos

// Seleccionar todos los elementos de preguntas
const faqQuestions = document.querySelectorAll('.faq-question');

faqQuestions.forEach(question => {
    question.addEventListener('click', () => {
        const answer = question.nextElementSibling;

        // Alternar la visibilidad de la respuesta
        if (answer.style.display === 'block') {
            answer.style.display = 'none';
        } else {
            answer.style.display = 'block';
        }
    });
});

