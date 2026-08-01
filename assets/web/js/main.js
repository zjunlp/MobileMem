/**
 * MobileMem project page interactions.
 *
 * Owns page-wide services only: analytics, language, video, and the
 * feature accordion. Interactive demos live in dedicated component files.
 */

// Optional page analytics ---------------------------------------------------

if (["http:", "https:"].includes(window.location.protocol)) {
  const busuanziScript = document.createElement("script");
  busuanziScript.defer = true;
  busuanziScript.src = "https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js";
  document.head.appendChild(busuanziScript);
}

const languageToggle = document.querySelector("[data-toggle-lang]");

// Shared language switch ----------------------------------------------------

const setLanguageToggle = (lang) => {
  if (!languageToggle) return;
  const nextLang = lang === "zh" ? "en" : "zh";
  languageToggle.dataset.toggleLang = nextLang;
  languageToggle.textContent = nextLang === "en" ? "English" : "Chinese";
  languageToggle.setAttribute(
    "aria-label",
    nextLang === "en" ? "Switch language to English" : "Switch language to Chinese",
  );
};

const setPageLanguage = (lang) => {
  const normalizedLang = lang === "zh" ? "zh" : "en";
  document.documentElement.lang = normalizedLang;
  document.body.classList.toggle("lang-zh", normalizedLang === "zh");
  document.body.classList.toggle("lang-en", normalizedLang === "en");
  setLanguageToggle(normalizedLang);
  window.dispatchEvent(
    new CustomEvent("mobilemem:languagechange", {
      detail: { lang: normalizedLang },
    }),
  );
};

languageToggle?.addEventListener("click", () => {
  setPageLanguage(languageToggle.dataset.toggleLang);
});

setPageLanguage(document.body.classList.contains("lang-zh") ? "zh" : "en");

// OPPO application video ----------------------------------------------------

const videoModal = document.querySelector("#oppo-video-modal");
const videoPlay = document.querySelector(".video-play");
const videoClose = document.querySelector(".video-close");
const oppoVideo = document.querySelector("[data-oppo-video]");

if (videoModal && videoPlay && videoClose) {
  videoPlay.addEventListener("click", () => {
    videoModal.showModal();
    if (oppoVideo) {
      oppoVideo.currentTime = 0;
      oppoVideo.play().catch(() => {});
    }
  });

  videoClose.addEventListener("click", () => {
    videoModal.close();
  });

  videoModal.addEventListener("click", (event) => {
    if (event.target === videoModal) videoModal.close();
  });

  videoModal.addEventListener("close", () => {
    if (!oppoVideo) return;
    oppoVideo.pause();
    oppoVideo.currentTime = 0;
  });
}

// Highlight accordion -------------------------------------------------------

const featureDetails = Array.from(document.querySelectorAll(".feature-accordion details"));

featureDetails.forEach((details) => {
  const summary = details.querySelector("summary");
  if (!summary) return;

  summary.addEventListener("click", (event) => {
    event.preventDefault();
    if (details.open) return;

    featureDetails.forEach((item) => {
      item.open = item === details;
    });
  });
});
