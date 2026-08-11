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
const languageStorageKey = "mobilemem-language";

// Shared language switch ----------------------------------------------------

const getSavedLanguage = () => {
  try {
    const language = window.localStorage.getItem(languageStorageKey);
    return language === "zh" || language === "en" ? language : null;
  } catch {
    return null;
  }
};

const saveLanguage = (language) => {
  try {
    window.localStorage.setItem(languageStorageKey, language);
  } catch {
    // Language switching still works when storage is unavailable.
  }
};

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
        ? "技术报告，即将发布"
        : "Tech Report, coming soon"
      : isChinese
        ? "技术报告"
        : "Tech Report",
  );
  if (isPlaceholder) reportLink.title = isChinese ? "即将发布" : "Coming soon";
  else reportLink.removeAttribute("title");
};

const setPageLanguage = (lang, { persist = true } = {}) => {
  const normalizedLang = lang === "zh" ? "zh" : "en";
  document.documentElement.lang = normalizedLang;
  document.body.classList.toggle("lang-zh", normalizedLang === "zh");
  document.body.classList.toggle("lang-en", normalizedLang === "en");
  if (persist) saveLanguage(normalizedLang);
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

window.addEventListener("storage", (event) => {
  if (event.key !== languageStorageKey || !event.newValue) return;
  setPageLanguage(event.newValue, { persist: false });
});

setPageLanguage(getSavedLanguage() || (document.body.classList.contains("lang-zh") ? "zh" : "en"));

// Hero statistics ----------------------------------------------------------

const countUpValues = Array.from(document.querySelectorAll("[data-count-to]"));
const countUpRegion = document.querySelector(".hero-stats");

const formatCountValue = (element, value) => {
  const decimals = Number(element.dataset.countDecimals || 0);
  return `${value.toFixed(decimals)}${element.dataset.countSuffix || ""}`;
};

const animateCountValue = (element, index) => {
  const target = Number(element.dataset.countTo);
  if (!Number.isFinite(target)) return;

  const duration = 1050;
  const delay = index * 120;
  let startTime;

  element.textContent = formatCountValue(element, 0);

  const update = (time) => {
    if (startTime === undefined) startTime = time + delay;
    if (time < startTime) {
      window.requestAnimationFrame(update);
      return;
    }

    const progress = Math.min((time - startTime) / duration, 1);
    const easedProgress = 1 - Math.pow(1 - progress, 3);
    element.textContent = formatCountValue(element, target * easedProgress);

    if (progress < 1) window.requestAnimationFrame(update);
    else element.textContent = formatCountValue(element, target);
  };

  window.requestAnimationFrame(update);
};

countUpValues.forEach((element) => {
  const target = Number(element.dataset.countTo);
  if (Number.isFinite(target)) element.textContent = formatCountValue(element, target);
});

if (
  countUpRegion &&
  countUpValues.length &&
  !window.matchMedia("(prefers-reduced-motion: reduce)").matches
) {
  if ("IntersectionObserver" in window) {
    const countUpObserver = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        countUpValues.forEach(animateCountValue);
        countUpObserver.disconnect();
      },
      { threshold: 0.35 },
    );
    countUpObserver.observe(countUpRegion);
  } else {
    countUpValues.forEach(animateCountValue);
  }
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
