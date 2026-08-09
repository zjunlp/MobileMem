/**
 * MobileMem project page interactions.
 *
 * Owns page-wide services only: analytics, language, video, and the
 * feature accordion. Interactive demos live in dedicated component files.
 */

// Optional page analytics ---------------------------------------------------

const pageViewCounter = document.querySelector("#busuanzi_value_page_pv");
const isLocalPreview = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);

if (["http:", "https:"].includes(window.location.protocol) && !isLocalPreview) {
  const busuanziScript = document.createElement("script");
  busuanziScript.defer = true;
  busuanziScript.src = "https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js";
  document.head.appendChild(busuanziScript);
} else if (pageViewCounter) {
  pageViewCounter.textContent = "—";
}

const languageToggle = document.querySelector("[data-toggle-lang]");
const reportLink = document.querySelector("[data-report-link]");

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

const setReportLink = (lang) => {
  if (!reportLink) return;
  const isChinese = lang === "zh";
  const href = isChinese ? reportLink.dataset.reportHrefZh : reportLink.dataset.reportHrefEn;
  const isPlaceholder = !href || href === "#";
  reportLink.href = href || "#";
  reportLink.toggleAttribute("aria-disabled", isPlaceholder);
  reportLink.setAttribute(
    "aria-label",
    isPlaceholder
      ? isChinese
        ? "白皮书，即将发布"
        : "Technical Report, coming soon"
      : isChinese
        ? "白皮书"
        : "Technical Report",
  );
  if (isPlaceholder) reportLink.title = isChinese ? "即将发布" : "Coming soon";
  else reportLink.removeAttribute("title");
};

const setPageLanguage = (lang) => {
  const normalizedLang = lang === "zh" ? "zh" : "en";
  document.documentElement.lang = normalizedLang;
  document.body.classList.toggle("lang-zh", normalizedLang === "zh");
  document.body.classList.toggle("lang-en", normalizedLang === "en");
  setLanguageToggle(normalizedLang);
  setReportLink(normalizedLang);
  window.dispatchEvent(
    new CustomEvent("mobilemem:languagechange", {
      detail: { lang: normalizedLang },
    }),
  );
};

languageToggle?.addEventListener("click", () => {
  setPageLanguage(languageToggle.dataset.toggleLang);
});

reportLink?.addEventListener("click", (event) => {
  if (reportLink.getAttribute("href") === "#") event.preventDefault();
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
const featureVisualImage = document.querySelector("#feature-visual-image");
let featureVisualRequestId = 0;

const featureVisualAlt = (details) => {
  const lang = document.documentElement.lang === "zh" ? "zh" : "en";
  return details.dataset[lang === "zh" ? "featureAltZh" : "featureAltEn"] || "";
};

const updateFeatureVisual = (details) => {
  if (!featureVisualImage || !details?.dataset.featureVisual) return;

  const source = details.dataset.featureVisual;
  featureVisualImage.alt = featureVisualAlt(details);
  if (featureVisualImage.getAttribute("src") === source) return;

  featureVisualRequestId += 1;
  const requestId = featureVisualRequestId;
  const preload = new Image();
  let applied = false;

  const applyVisual = () => {
    if (applied || requestId !== featureVisualRequestId) return;
    applied = true;
    featureVisualImage.src = source;
    featureVisualImage.width = Number(details.dataset.featureWidth);
    featureVisualImage.height = Number(details.dataset.featureHeight);
    featureVisualImage.alt = featureVisualAlt(details);
    window.requestAnimationFrame(() => featureVisualImage.classList.remove("is-swapping"));
  };

  featureVisualImage.classList.add("is-swapping");
  preload.addEventListener("load", applyVisual, { once: true });
  preload.addEventListener(
    "error",
    () => {
      if (requestId === featureVisualRequestId) {
        featureVisualImage.classList.remove("is-swapping");
      }
    },
    { once: true },
  );
  preload.src = source;
  if (preload.complete) applyVisual();
};

featureDetails.forEach((details) => {
  const summary = details.querySelector("summary");
  if (!summary) return;

  summary.addEventListener("click", (event) => {
    event.preventDefault();
    if (details.open) return;

    featureDetails.forEach((item) => {
      item.open = item === details;
    });
    updateFeatureVisual(details);
  });
});

window.addEventListener("mobilemem:languagechange", () => {
  updateFeatureVisual(featureDetails.find((details) => details.open));
});
