/**
 * Interactive MobileMem sample browser.
 *
 * Ordered by configuration, DOM references, state, render helpers,
 * event bindings, and initialization.
 */

// Configuration and record model -------------------------------------------

(() => {
  const applicationData = globalThis.MobileMemApplicationData;
  if (!applicationData) {
    console.error("MobileMem application data failed to load.");
    return;
  }

  const {
    users: applicationUsers,
    categories: applicationCategoryOrder,
    typeCopy: applicationTypeCopy,
    categoryCounts: applicationCategoryCounts,
    identityLabels: applicationIdentityLabels,
    eventLabels: applicationEventLabels,
    previewCount: applicationPreviewCount,
    resolveAssetPath: applicationAssetPath,
  } = applicationData;

  const applicationRecords = applicationUsers.flatMap((uid) =>
    applicationCategoryOrder.flatMap((type) => {
      const copy = applicationTypeCopy[type];
      return Array.from({ length: applicationPreviewCount }, (_, sampleIndex) => {
        const sampleNumber = sampleIndex + 1;
        return {
          uid,
          type,
          sampleNumber,
          src: applicationAssetPath(uid, type, sampleNumber),
          title: copy.title,
        };
      });
    }),
  );

  // DOM references ----------------------------------------------------------

  const applicationShowcase = document.querySelector("[data-application-showcase]");
  const applicationItems = Array.from(document.querySelectorAll(".application-item"));
  const applicationImage = document.getElementById("application-visual-image");
  const applicationPosition = document.getElementById("application-phone-position");
  const applicationVisual = applicationShowcase?.querySelector(".application-phone-visual");
  const applicationPhone = document.querySelector(".application-phone");
  const applicationPhoneDesktop = document.querySelector("[data-application-phone-desktop]");
  const applicationAiDialogue = document.querySelector("[data-application-ai-dialogue]");
  const applicationAiEntry = document.querySelector("[data-application-phone-ai]");
  const applicationPhoneRecents = document.querySelector("[data-application-phone-recents]");
  const applicationRecentsImage = document.querySelector("[data-application-recents-image]");
  const applicationRecentsLabel = document.querySelector("[data-application-recents-label]");
  const applicationRecentsOpen = document.querySelector("[data-application-recents-open]");
  const applicationSystemButtons = Array.from(
    document.querySelectorAll("[data-application-system-action]"),
  );
  const applicationPhoneCount = document.querySelector("[data-application-phone-count]");
  const applicationPhoneCaption = document.querySelector("[data-application-phone-caption]");
  const applicationPhoneCaptionTitle = document.querySelector(
    "[data-application-phone-caption-title]",
  );
  const applicationPhoneDirectionButtons = Array.from(
    document.querySelectorAll("[data-application-phone-direction]"),
  );
  const applicationPhoneUidButtons = Array.from(
    document.querySelectorAll("[data-application-phone-uid]"),
  );
  const applicationAiUserAvatar = document.querySelector("[data-application-ai-user-avatar]");
  const applicationPhoneApps = Array.from(
    document.querySelectorAll("[data-application-phone-type]"),
  );
  const applicationOpen = document.querySelector("[data-application-open]");
  const applicationDirectionButtons = Array.from(
    document.querySelectorAll("[data-application-direction]"),
  );
  const applicationLightbox = document.getElementById("application-lightbox");
  const applicationLightboxImage = document.getElementById("application-lightbox-image");
  const applicationLightboxTitle = document.getElementById("application-lightbox-title");
  const applicationLightboxRecord = document.getElementById("application-lightbox-record");
  const applicationLightboxCount = document.getElementById("application-lightbox-count");
  const applicationClose = document.querySelector("[data-application-close]");
  const applicationLightboxMedia = document.querySelector(".application-lightbox-media");
  const applicationMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const applicationAiStream = document.querySelector("[data-application-ai-dialogue-stream]");
  const applicationAiSessionTitle = document.querySelector("[data-application-ai-session-title]");
  const applicationAiSessionTabs = document.querySelector("[data-application-ai-session-tabs]");
  const applicationAiHistory = document.querySelector("[data-application-ai-history]");
  const applicationAiHistoryOpen = document.querySelector("[data-application-ai-history-open]");
  const applicationAiHistoryClose = document.querySelector("[data-application-ai-history-close]");

  // Dialogue data -------------------------------------------------------------

  const applicationDialogueSamples = globalThis.applicationTrajectoryData || {};

  // Runtime state -----------------------------------------------------------

  let applicationImageTimer = 0;
  let applicationLang = document.body.classList.contains("lang-zh") ? "zh" : "en";
  let activeApplicationUid = "uid0";
  let activeApplicationType = "group_chat";
  let activeApplicationIndex = 0;
  let activeApplicationSessionIndex = 0;
  let visibleApplicationIndices = [];
  let applicationSwipeStartX = 0;
  let applicationSwipeStartY = 0;
  let applicationSwipeLockUntil = 0;

  // Labels and record helpers -------------------------------------------------

  const applicationValue = (record, key) =>
    record?.[key]?.[applicationLang] || record?.[key]?.en || "";

  const applicationAnnotationLabel = (record) => {
    if (!record) return "";
    const position = Math.max(0, record.sampleNumber - 1);
    if (record.type === "event") return applicationEventLabels[record.uid]?.[position] || "";
    if (record.type === "person" || record.type === "group_chat_members") {
      return applicationIdentityLabels[record.uid]?.[record.type]?.[position] || "";
    }
    return "";
  };

  const applicationRecordLabel = (record) =>
    `${record.uid} / ${record.type} / ${String(record.sampleNumber).padStart(2, "0")}`;

  const getVisibleApplicationIndices = () =>
    applicationRecords
      .map((record, index) => ({ record, index }))
      .filter(
        ({ record }) =>
          record.uid === activeApplicationUid && record.type === activeApplicationType,
      )
      .map(({ index }) => index);

  const applicationDialogueImageSources = (uid) => ({
    person: applicationAssetPath(uid, "person"),
    event: applicationAssetPath(uid, "event"),
    book: applicationAssetPath(uid, "book"),
    friend: applicationAssetPath(uid, "friend"),
    group_chat: applicationAssetPath(uid, "group_chat"),
    group_chat_alt: applicationAssetPath(uid, "group_chat", 2),
    member: applicationAssetPath(uid, "group_chat_members"),
    member_alt: applicationAssetPath(uid, "group_chat_members", 2),
    money: applicationAssetPath(uid, "money"),
    video: applicationAssetPath(uid, "video"),
    music: applicationAssetPath(uid, "music"),
    shopping: applicationAssetPath(uid, "shopping"),
    ticket: applicationAssetPath(uid, "ticket"),
  });

  // Dialogue rendering --------------------------------------------------------

  const setApplicationAiHistory = (open, { focusTrigger = false } = {}) => {
    if (!applicationAiHistory) return;
    applicationAiHistory.hidden = !open;
    applicationAiHistory.setAttribute("aria-hidden", String(!open));
    applicationAiHistoryOpen?.setAttribute("aria-expanded", String(open));

    if (open) {
      requestAnimationFrame(() => {
        applicationAiSessionTabs?.querySelector("button.is-active")?.focus({ preventScroll: true });
      });
    } else if (focusTrigger) {
      applicationAiHistoryOpen?.focus({ preventScroll: true });
    }
  };

  const renderApplicationDialogue = () => {
    const source =
      applicationDialogueSamples[activeApplicationUid] || applicationDialogueSamples.uid0 || [];
    const sessions = (Array.isArray(source) ? source : [source]).filter(Boolean);
    if (!sessions.length || !applicationAiStream) return;

    activeApplicationSessionIndex = Math.min(activeApplicationSessionIndex, sessions.length - 1);
    const sample = sessions[activeApplicationSessionIndex];

    if (applicationAiSessionTabs) {
      const tabs = document.createDocumentFragment();
      sessions.slice(0, 5).forEach((session, index) => {
        const button = document.createElement("button");
        const active = index === activeApplicationSessionIndex;
        const avatar = document.createElement("span");
        const avatarImage = document.createElement("img");
        const copy = document.createElement("span");
        const title = document.createElement("strong");
        const time = document.createElement("small");
        const indicator = document.createElement("span");

        button.type = "button";
        button.className = `application-ai-history-item${active ? " is-active" : ""}`;
        button.setAttribute("aria-label", session.title);
        if (active) button.setAttribute("aria-current", "true");

        avatar.className = "application-ai-history-avatar";
        avatarImage.src = "assets/web/xiaobu-avatar.png";
        avatarImage.alt = "";
        avatar.append(avatarImage);

        copy.className = "application-ai-history-copy";
        title.textContent = session.title;
        time.textContent = session.date;
        copy.append(title, time);

        indicator.className = "application-ai-history-indicator";
        indicator.setAttribute("aria-hidden", "true");
        button.append(avatar, copy, indicator);

        button.addEventListener("click", () => {
          activeApplicationSessionIndex = index;
          renderApplicationDialogue();
          setApplicationAiHistory(false, { focusTrigger: true });
        });
        tabs.append(button);
      });
      applicationAiSessionTabs.replaceChildren(tabs);
    }

    if (applicationAiSessionTitle) applicationAiSessionTitle.textContent = sample.title;
    applicationAiHistoryOpen?.setAttribute(
      "aria-label",
      applicationLang === "zh" ? "打开历史对话" : "Open dialogue history",
    );
    applicationAiHistoryClose?.setAttribute(
      "aria-label",
      applicationLang === "zh" ? "关闭历史对话" : "Close dialogue history",
    );
    applicationAiSessionTabs?.setAttribute(
      "aria-label",
      applicationLang === "zh" ? "选择一条历史对话" : "Choose a dialogue session",
    );
    const imageSources = applicationDialogueImageSources(activeApplicationUid);
    const fragment = document.createDocumentFragment();

    sample.messages.forEach(([role, content, imageType], index) => {
      const article = document.createElement("article");
      const avatar = document.createElement("span");
      const avatarImage = document.createElement("img");
      article.className = role === "user" ? "is-user" : "is-ai";
      article.dataset.turn = String(index + 1).padStart(2, "0");

      avatar.className = "application-ai-message-avatar";
      avatarImage.src =
        role === "user"
          ? applicationAssetPath(activeApplicationUid, "person")
          : "assets/web/xiaobu-avatar.png";
      avatarImage.alt = "";
      avatarImage.className = role === "user" ? "is-user" : "is-xiaobu";
      avatar.append(avatarImage);
      article.append(avatar);

      if (imageType) {
        const imageBubble = document.createElement("div");
        imageBubble.className = "application-ai-image-bubble";
        const image = document.createElement("img");
        const localAsset = imageType.match(
          /^assets\/web\/memweb\/(?:curated\/)?(uid\d+)-(.+)-(\d{2})\.png$/,
        );
        image.src = localAsset
          ? applicationAssetPath(localAsset[1], localAsset[2], Number(localAsset[3]))
          : imageType.startsWith("assets/")
            ? imageType
            : imageSources[imageType] || imageSources.event;
        image.alt =
          applicationLang === "zh" ? "该轮发送的数据集图片" : "Dataset image sent in this turn";
        image.loading = "lazy";
        imageBubble.append(image);
        article.append(imageBubble);
      } else {
        const bubble = document.createElement("p");
        bubble.textContent = content;
        article.append(bubble);
      }

      fragment.append(article);
    });

    applicationAiStream.replaceChildren(fragment);
    applicationAiStream.scrollTop = 0;
  };

  // Phone synchronization -----------------------------------------------------

  const setApplicationPhoneMode = (mode) => {
    const atHome = mode === "home";
    const atRecord = mode === "record";
    const atRecents = mode === "recents";
    const atDialogue = mode === "dialogue";
    if (!atDialogue) setApplicationAiHistory(false);
    if (applicationPhone) {
      applicationPhone.dataset.applicationPhoneMode = atHome
        ? "home"
        : atRecents
          ? "recents"
          : atDialogue
            ? "dialogue"
            : "record";
    }
    if (applicationPhoneDesktop) applicationPhoneDesktop.hidden = !atHome;
    if (applicationAiDialogue) applicationAiDialogue.hidden = !atDialogue;
    if (applicationPhoneRecents) applicationPhoneRecents.hidden = !atRecents;
    if (applicationPhoneCount) applicationPhoneCount.hidden = !atRecord;
    const annotationLabel = atRecord
      ? applicationAnnotationLabel(applicationRecords[activeApplicationIndex])
      : "";
    if (applicationPhoneCaptionTitle) applicationPhoneCaptionTitle.textContent = annotationLabel;
    if (applicationPhoneCaption) applicationPhoneCaption.hidden = !annotationLabel;
    applicationPhoneDirectionButtons.forEach((button) => {
      button.hidden = !atRecord;
    });
    if (applicationOpen) applicationOpen.hidden = !atRecord;
  };

  const syncApplicationDirectory = () => {
    const counts = applicationCategoryCounts[activeApplicationUid] || {};
    const userTotal = Object.values(counts).reduce((sum, count) => sum + count, 0);

    if (applicationPhone) applicationPhone.dataset.applicationUid = activeApplicationUid;

    applicationPhoneApps.forEach((button) => {
      const type = button.dataset.applicationPhoneType;
      const preview = button.querySelector("img");
      if (preview) {
        preview.src = applicationAssetPath(activeApplicationUid, type);
        preview.alt = "";
      }
    });

    if (applicationAiUserAvatar) {
      applicationAiUserAvatar.src = applicationAssetPath(activeApplicationUid, "person");
    }

    applicationPhoneUidButtons.forEach((button) => {
      const active = button.dataset.applicationPhoneUid === activeApplicationUid;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });

    // Keep the total available to assistive tooling without adding visual chrome.
    applicationPhone?.setAttribute("data-application-total", String(userTotal));
  };

  const syncApplicationVisual = (recordIndex, animate = true) => {
    const record = applicationRecords[recordIndex];
    if (!record) return;

    activeApplicationIndex = recordIndex;
    activeApplicationUid = record.uid;
    activeApplicationType = record.type;
    visibleApplicationIndices = getVisibleApplicationIndices();

    const position = Math.max(0, visibleApplicationIndices.indexOf(recordIndex));
    const count = `${String(position + 1).padStart(2, "0")} / ${String(visibleApplicationIndices.length).padStart(2, "0")}`;
    const typeLabel =
      applicationTypeCopy[record.type]?.[applicationLang] ||
      applicationTypeCopy[record.type]?.en ||
      record.type;
    const title = applicationValue(record, "title");
    const recordLabel = applicationRecordLabel(record);
    const nextAlt = `MemWeb ${applicationTypeCopy[record.type]?.en || record.type} screenshot from ${record.uid}.`;

    syncApplicationDirectory();
    if (applicationPosition) applicationPosition.textContent = count;
    const annotationLabel = applicationAnnotationLabel(record);
    if (applicationPhoneCaptionTitle) applicationPhoneCaptionTitle.textContent = annotationLabel;
    if (applicationPhoneCaption) {
      const atRecord = applicationPhone?.dataset.applicationPhoneMode === "record";
      applicationPhoneCaption.hidden = !atRecord || !annotationLabel;
    }
    if (applicationLightboxTitle) applicationLightboxTitle.textContent = title;
    if (applicationLightboxRecord) applicationLightboxRecord.textContent = recordLabel;
    if (applicationLightboxCount) applicationLightboxCount.textContent = count;
    if (applicationRecentsImage) {
      applicationRecentsImage.src = record.src;
      applicationRecentsImage.alt = nextAlt;
    }
    if (applicationRecentsLabel)
      applicationRecentsLabel.textContent = `${typeLabel} · ${record.uid.toUpperCase()}`;
    if (applicationOpen) {
      applicationOpen.dataset.recordType = record.type;
      applicationOpen.setAttribute(
        "aria-label",
        applicationLang === "zh" ? `查看原始截图：${title}` : `Open original screenshot: ${title}`,
      );
    }

    if (applicationLightboxImage) {
      applicationLightboxImage.src = record.src;
      applicationLightboxImage.alt = nextAlt;
    }

    window.clearTimeout(applicationImageTimer);
    if (applicationImage) {
      applicationImage.alt = nextAlt;
      if (
        !animate ||
        applicationMotionQuery.matches ||
        applicationImage.getAttribute("src") === record.src
      ) {
        applicationImage.src = record.src;
        applicationImage.classList.remove("is-switching");
      } else {
        applicationImage.classList.add("is-switching");
        applicationImageTimer = window.setTimeout(() => {
          applicationImage.src = record.src;
          requestAnimationFrame(() => applicationImage.classList.remove("is-switching"));
        }, 90);
      }
    }

    if (typeof Image === "function" && visibleApplicationIndices.length > 1) {
      [-1, 1].forEach((offset) => {
        const nearbyPosition =
          (position + offset + visibleApplicationIndices.length) % visibleApplicationIndices.length;
        const nearbyRecord = applicationRecords[visibleApplicationIndices[nearbyPosition]];
        if (!nearbyRecord) return;
        const preload = new Image();
        preload.src = nearbyRecord.src;
      });
    }
  };

  const activateApplication = (index, { animate = true } = {}) => {
    if (!applicationRecords.length) return;
    const normalizedIndex = (index + applicationRecords.length) % applicationRecords.length;
    syncApplicationVisual(normalizedIndex, animate);
  };

  const moveApplication = (direction) => {
    visibleApplicationIndices = getVisibleApplicationIndices();
    if (!visibleApplicationIndices.length) return;
    const currentPosition = Math.max(0, visibleApplicationIndices.indexOf(activeApplicationIndex));
    const nextPosition =
      (currentPosition + direction + visibleApplicationIndices.length) %
      visibleApplicationIndices.length;
    activateApplication(visibleApplicationIndices[nextPosition], {
      animate: true,
    });
  };

  // Event bindings ------------------------------------------------------------

  applicationItems.forEach((details) => {
    const summary = details.querySelector("summary");
    if (!summary) return;

    summary.addEventListener("click", (event) => {
      event.preventDefault();
      if (details.open) return;

      applicationItems.forEach((item) => {
        item.open = item === details;
      });

      details.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        behavior: applicationMotionQuery.matches ? "auto" : "smooth",
      });
    });
  });

  applicationPhoneApps.forEach((button) => {
    button.addEventListener("click", () => {
      const nextType = button.dataset.applicationPhoneType;
      const recordIndex = applicationRecords.findIndex(
        (record) => record.uid === activeApplicationUid && record.type === nextType,
      );
      if (recordIndex < 0) return;
      activateApplication(recordIndex, { animate: true });
      setApplicationPhoneMode("record");
    });
  });

  applicationAiEntry?.addEventListener("click", () => {
    setApplicationAiHistory(false);
    renderApplicationDialogue();
    setApplicationPhoneMode("dialogue");
  });

  applicationAiHistoryOpen?.addEventListener("click", () => {
    setApplicationAiHistory(true);
  });

  applicationAiHistoryClose?.addEventListener("click", () => {
    setApplicationAiHistory(false, { focusTrigger: true });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || applicationAiHistory?.hidden) return;
    event.preventDefault();
    setApplicationAiHistory(false, { focusTrigger: true });
  });

  applicationPhoneUidButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextUid = button.dataset.applicationPhoneUid;
      const recordIndex = applicationRecords.findIndex(
        (record) => record.uid === nextUid && record.type === activeApplicationType,
      );
      if (recordIndex < 0) return;
      activeApplicationSessionIndex = 0;
      activateApplication(recordIndex, { animate: false });
      renderApplicationDialogue();
    });
  });

  applicationSystemButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.applicationSystemAction;
      const currentMode = applicationPhone?.dataset.applicationPhoneMode || "home";
      if (action === "home") {
        setApplicationPhoneMode("home");
        return;
      }
      if (action === "recents") {
        if (applicationPhone) applicationPhone.dataset.applicationPreviousMode = currentMode;
        setApplicationPhoneMode("recents");
        return;
      }
      if (action === "back" && currentMode === "recents") {
        setApplicationPhoneMode(applicationPhone?.dataset.applicationPreviousMode || "home");
        return;
      }
      if (action === "back" && currentMode === "dialogue" && !applicationAiHistory?.hidden) {
        setApplicationAiHistory(false, { focusTrigger: true });
        return;
      }
      if (action === "back" && ["record", "dialogue"].includes(currentMode))
        setApplicationPhoneMode("home");
    });
  });

  applicationRecentsOpen?.addEventListener("click", () => {
    setApplicationPhoneMode(applicationPhone?.dataset.applicationPreviousMode || "home");
  });

  applicationDirectionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      moveApplication(button.dataset.applicationDirection === "previous" ? -1 : 1);
    });
  });

  applicationVisual?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    moveApplication(event.key === "ArrowLeft" ? -1 : 1);
  });

  const openApplicationLightbox = () => {
    if (!applicationLightbox) return;
    if (typeof applicationLightbox.showModal === "function") applicationLightbox.showModal();
    else applicationLightbox.setAttribute("open", "");
  };

  const closeApplicationLightbox = () => {
    if (!applicationLightbox) return;
    if (typeof applicationLightbox.close === "function") applicationLightbox.close();
    else applicationLightbox.removeAttribute("open");
  };

  applicationOpen?.addEventListener("click", () => {
    if (Date.now() < applicationSwipeLockUntil) return;
    openApplicationLightbox();
  });
  applicationClose?.addEventListener("click", closeApplicationLightbox);
  applicationLightbox?.addEventListener("click", (event) => {
    if (event.target === applicationLightbox) closeApplicationLightbox();
  });
  applicationLightbox?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    moveApplication(event.key === "ArrowLeft" ? -1 : 1);
  });

  const bindApplicationSwipe = (element) => {
    if (!element) return;
    element.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "touch") return;
      applicationSwipeStartX = event.clientX;
      applicationSwipeStartY = event.clientY;
    });
    element.addEventListener("pointerup", (event) => {
      if (event.pointerType !== "touch") return;
      const deltaX = event.clientX - applicationSwipeStartX;
      const deltaY = event.clientY - applicationSwipeStartY;
      if (Math.abs(deltaX) < 46 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
      event.preventDefault();
      applicationSwipeLockUntil = Date.now() + 360;
      moveApplication(deltaX > 0 ? -1 : 1);
    });
  };

  bindApplicationSwipe(applicationOpen);
  bindApplicationSwipe(applicationLightboxMedia);

  // Language and motion -------------------------------------------------------

  const setApplicationLanguage = (lang) => {
    applicationLang = lang === "zh" ? "zh" : "en";
    const languageUids =
      applicationLang === "zh" ? ["uid0", "uid1", "uid2"] : ["uid10", "uid11", "uid12"];
    let nextIndex = activeApplicationIndex;
    if (!languageUids.includes(activeApplicationUid)) {
      nextIndex = applicationRecords.findIndex(
        (record) => record.uid === languageUids[0] && record.type === activeApplicationType,
      );
    }
    syncApplicationVisual(nextIndex >= 0 ? nextIndex : activeApplicationIndex, false);
    renderApplicationDialogue();
  };

  window.addEventListener("mobilemem:languagechange", (event) => {
    setApplicationLanguage(event.detail?.lang);
  });

  const initApplicationMotion = () => {
    if (
      !applicationShowcase ||
      !window.gsap ||
      !window.ScrollTrigger ||
      applicationMotionQuery.matches
    )
      return;
    gsap.registerPlugin(ScrollTrigger);
    gsap.fromTo(
      applicationShowcase,
      { autoAlpha: 0, y: 28 },
      {
        autoAlpha: 1,
        y: 0,
        duration: 0.72,
        ease: "power3.out",
        scrollTrigger: {
          trigger: applicationShowcase,
          start: "top 78%",
          once: true,
        },
      },
    );
  };

  // Initialization ------------------------------------------------------------

  activateApplication(activeApplicationIndex, { animate: false });
  setApplicationLanguage(applicationLang);
  setApplicationPhoneMode("home");
  window.addEventListener("load", initApplicationMotion, { once: true });
})();
