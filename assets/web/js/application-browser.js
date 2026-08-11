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
  const applicationCaseLimit = Math.min(applicationPreviewCount, 2);

  const applicationRecords = applicationUsers.flatMap((uid) =>
    applicationCategoryOrder.flatMap((type) => {
      const copy = applicationTypeCopy[type];
      return Array.from({ length: applicationCaseLimit }, (_, sampleIndex) => {
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
  const applicationSection = document.getElementById("application");
  const applicationItems = Array.from(document.querySelectorAll(".application-item"));
  const applicationImage = document.getElementById("application-visual-image");
  const applicationPosition = document.getElementById("application-phone-position");
  const applicationVisual = applicationShowcase?.querySelector(".application-phone-visual");
  const applicationPhone = applicationVisual?.querySelector(".application-phone");
  const applicationPhoneDesktop = applicationVisual?.querySelector(
    "[data-application-phone-desktop]",
  );
  const applicationAiDialogue = applicationVisual?.querySelector("[data-application-ai-dialogue]");
  const applicationAiEntry = applicationVisual?.querySelector("[data-application-phone-ai]");
  const applicationPhoneRecents = applicationVisual?.querySelector(
    "[data-application-phone-recents]",
  );
  const applicationRecentsImage = applicationVisual?.querySelector(
    "[data-application-recents-image]",
  );
  const applicationRecentsLabel = applicationVisual?.querySelector(
    "[data-application-recents-label]",
  );
  const applicationRecentsOpen = applicationVisual?.querySelector(
    "[data-application-recents-open]",
  );
  const applicationSystemButtons = Array.from(
    applicationVisual?.querySelectorAll("[data-application-system-action]") || [],
  );
  const applicationPhoneCount = applicationVisual?.querySelector("[data-application-phone-count]");
  const applicationPhoneCaption = applicationVisual?.querySelector(
    "[data-application-phone-caption]",
  );
  const applicationPhoneCaptionTitle = applicationVisual?.querySelector(
    "[data-application-phone-caption-title]",
  );
  const applicationPhoneDirectionButtons = Array.from(
    applicationVisual?.querySelectorAll("[data-application-phone-direction]") || [],
  );
  const applicationPhoneUidButtons = Array.from(
    applicationVisual?.querySelectorAll("[data-application-phone-uid]") || [],
  );
  const applicationAiUserAvatar = applicationVisual?.querySelector(
    "[data-application-ai-user-avatar]",
  );
  const applicationPhoneApps = Array.from(
    applicationVisual?.querySelectorAll("[data-application-phone-type]") || [],
  );
  const applicationOpen = applicationVisual?.querySelector("[data-application-open]");
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
  const applicationAiStream = applicationVisual?.querySelector(
    "[data-application-ai-dialogue-stream]",
  );
  const applicationAiSessionTitle = applicationVisual?.querySelector(
    "[data-application-ai-session-title]",
  );
  const applicationAiSessionTabs = applicationVisual?.querySelector(
    "[data-application-ai-session-tabs]",
  );
  const applicationAiHistory = applicationVisual?.querySelector("[data-application-ai-history]");
  const applicationAiHistoryOpen = applicationVisual?.querySelector(
    "[data-application-ai-history-open]",
  );
  const applicationAiHistoryClose = applicationVisual?.querySelector(
    "[data-application-ai-history-close]",
  );
  const datasetCaseDialog = document.getElementById("dataset-case-dialog");
  const datasetCaseOpen = document.querySelector("[data-dataset-case-open]");
  const datasetCaseClose = document.querySelector("[data-dataset-case-close]");

  // Dialogue data -------------------------------------------------------------

  const applicationDialogueSamples = globalThis.applicationTrajectoryData || {};

  // Runtime state -----------------------------------------------------------

  let applicationImageRequestId = 0;
  let applicationLang = document.body.classList.contains("lang-zh") ? "zh" : "en";
  let activeApplicationUid = "uid0";
  let activeApplicationType = "group_chat";
  let activeApplicationIndex = 0;
  let activeApplicationSessionIndex = 0;
  let visibleApplicationIndices = [];
  let applicationSwipeStartX = 0;
  let applicationSwipeStartY = 0;
  let applicationSwipeLockUntil = 0;
  let applicationAssetsReady = false;
  const applicationImagePreloads = new Map();

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

  const setApplicationImageSource = (image, source) => {
    if (!image || !source) return;
    if (applicationAssetsReady) {
      image.src = source;
      image.removeAttribute("data-src");
      return;
    }
    image.dataset.src = source;
    image.removeAttribute("src");
  };

  const hydrateApplicationImages = () => {
    applicationSection?.querySelectorAll("img[data-src]").forEach((image) => {
      image.src = image.dataset.src;
      image.removeAttribute("data-src");
    });
  };

  const preloadApplicationImage = (source) => {
    if (!source || typeof Image !== "function") return Promise.resolve(Boolean(source));
    if (applicationImagePreloads.has(source)) return applicationImagePreloads.get(source);

    const request = new Promise((resolve) => {
      const image = new Image();
      image.decoding = "async";
      image.addEventListener("load", () => resolve(true), { once: true });
      image.addEventListener(
        "error",
        () => {
          applicationImagePreloads.delete(source);
          resolve(false);
        },
        { once: true },
      );
      image.src = source;
    });
    applicationImagePreloads.set(source, request);
    return request;
  };

  const preloadApplicationGroup = (uid, type) => {
    for (let sampleNumber = 1; sampleNumber <= applicationCaseLimit; sampleNumber += 1) {
      preloadApplicationImage(applicationAssetPath(uid, type, sampleNumber));
    }
  };

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
        avatarImage.src = "assets/web/xiaobu-avatar.webp";
        avatarImage.alt = "";
        avatarImage.loading = "lazy";
        avatarImage.decoding = "async";
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
          : "assets/web/xiaobu-avatar.webp";
      avatarImage.alt = "";
      avatarImage.className = role === "user" ? "is-user" : "is-xiaobu";
      avatarImage.loading = "lazy";
      avatarImage.decoding = "async";
      avatar.append(avatarImage);
      article.append(avatar);

      if (imageType) {
        const imageBubble = document.createElement("div");
        imageBubble.className = "application-ai-image-bubble";
        const image = document.createElement("img");
        const localAsset = imageType.match(
          /^assets\/web\/memweb\/(?:curated\/)?(uid\d+)-(.+)-(\d{2})\.(?:png|webp)$/,
        );
        image.src = localAsset
          ? applicationAssetPath(localAsset[1], localAsset[2], Number(localAsset[3]))
          : imageType.startsWith("assets/")
            ? imageType
            : imageSources[imageType] || imageSources.event;
        image.alt =
          applicationLang === "zh" ? "该轮发送的数据集图片" : "Dataset image sent in this turn";
        image.loading = "lazy";
        image.decoding = "async";
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
        setApplicationImageSource(preview, applicationAssetPath(activeApplicationUid, type));
        preview.alt = "";
      }
    });

    if (applicationAiUserAvatar) {
      setApplicationImageSource(
        applicationAiUserAvatar,
        applicationAssetPath(activeApplicationUid, "person"),
      );
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
      setApplicationImageSource(applicationRecentsImage, record.src);
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
      setApplicationImageSource(applicationLightboxImage, record.src);
      applicationLightboxImage.alt = nextAlt;
    }

    applicationImageRequestId += 1;
    const imageRequestId = applicationImageRequestId;
    if (applicationImage) {
      const commitApplicationImage = () => {
        if (imageRequestId !== applicationImageRequestId) return;
        applicationImage.src = record.src;
        applicationImage.alt = nextAlt;
        applicationImage.removeAttribute("data-src");
      };

      applicationImage.classList.remove("is-switching");
      if (
        !animate ||
        applicationMotionQuery.matches ||
        applicationImage.getAttribute("src") === record.src
      ) {
        commitApplicationImage();
      } else {
        preloadApplicationImage(record.src).then((loaded) => {
          if (!loaded || imageRequestId !== applicationImageRequestId) return;
          applicationImage.classList.add("is-switching");
          requestAnimationFrame(() => {
            if (imageRequestId !== applicationImageRequestId) return;
            commitApplicationImage();
            requestAnimationFrame(() => {
              if (imageRequestId === applicationImageRequestId) {
                applicationImage.classList.remove("is-switching");
              }
            });
          });
        });
      }
    }

    if (applicationAssetsReady) preloadApplicationGroup(record.uid, record.type);
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
    const preloadGroup = () =>
      preloadApplicationGroup(activeApplicationUid, button.dataset.applicationPhoneType);
    button.addEventListener("pointerenter", preloadGroup);
    button.addEventListener("focus", preloadGroup);
    button.addEventListener("click", () => {
      const nextType = button.dataset.applicationPhoneType;
      preloadGroup();
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
    const preloadGroup = () =>
      preloadApplicationGroup(button.dataset.applicationPhoneUid, activeApplicationType);
    button.addEventListener("pointerenter", preloadGroup);
    button.addEventListener("focus", preloadGroup);
    button.addEventListener("click", () => {
      const nextUid = button.dataset.applicationPhoneUid;
      preloadGroup();
      const recordIndex = applicationRecords.findIndex(
        (record) => record.uid === nextUid && record.type === activeApplicationType,
      );
      if (recordIndex < 0) return;
      activeApplicationSessionIndex = 0;
      activateApplication(recordIndex, { animate: false });
      if (applicationPhone?.dataset.applicationPhoneMode === "dialogue") {
        renderApplicationDialogue();
      }
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

  const openDatasetCases = () => {
    if (!datasetCaseDialog || datasetCaseDialog.open) return;
    applicationAssetsReady = true;
    hydrateApplicationImages();
    syncApplicationVisual(activeApplicationIndex, false);
    setApplicationPhoneMode("home");
    if (typeof datasetCaseDialog.showModal === "function") datasetCaseDialog.showModal();
    else datasetCaseDialog.setAttribute("open", "");
  };

  const closeDatasetCases = () => {
    if (!datasetCaseDialog) return;
    if (typeof datasetCaseDialog.close === "function") datasetCaseDialog.close();
    else datasetCaseDialog.removeAttribute("open");
  };

  datasetCaseOpen?.addEventListener("click", openDatasetCases);
  datasetCaseClose?.addEventListener("click", closeDatasetCases);
  datasetCaseDialog?.addEventListener("click", (event) => {
    if (event.target === datasetCaseDialog) closeDatasetCases();
  });

  // Language and motion -------------------------------------------------------

  const setApplicationLanguage = (lang) => {
    applicationLang = lang === "zh" ? "zh" : "en";
    const languageUids = applicationLang === "zh" ? ["uid0"] : ["uid10"];
    let nextIndex = activeApplicationIndex;
    if (!languageUids.includes(activeApplicationUid)) {
      nextIndex = applicationRecords.findIndex(
        (record) => record.uid === languageUids[0] && record.type === activeApplicationType,
      );
    }
    syncApplicationVisual(nextIndex >= 0 ? nextIndex : activeApplicationIndex, false);
    if (applicationPhone?.dataset.applicationPhoneMode === "dialogue") {
      renderApplicationDialogue();
    }
    datasetCaseClose?.setAttribute(
      "aria-label",
      applicationLang === "zh" ? "关闭数据集案例" : "Close dataset cases",
    );
    applicationPhoneUidButtons.forEach((button) => {
      const isChineseCase = button.dataset.applicationPhoneUid === "uid0";
      const label =
        applicationLang === "zh"
          ? isChineseCase
            ? "中文数据集案例"
            : "英文数据集案例"
          : isChineseCase
            ? "Chinese dataset case"
            : "English dataset case";
      button.setAttribute("aria-label", label);
      button.title = label;
    });
  };

  window.addEventListener("mobilemem:languagechange", (event) => {
    setApplicationLanguage(event.detail?.lang);
  });

  const initApplicationMotion = () => {
    if (!applicationShowcase || applicationMotionQuery.matches) return;

    const playEntrance = () => {
      applicationShowcase.animate(
        [
          { opacity: 0, transform: "translateY(28px)" },
          { opacity: 1, transform: "translateY(0)" },
        ],
        {
          duration: 720,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
          fill: "both",
        },
      );
    };

    if (typeof IntersectionObserver !== "function") {
      playEntrance();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        playEntrance();
        observer.disconnect();
      },
      { rootMargin: "0px 0px -22%" },
    );
    observer.observe(applicationShowcase);
  };

  const initApplicationPreloading = () => {
    if (!applicationShowcase) return;
    if (typeof IntersectionObserver !== "function") {
      applicationAssetsReady = true;
      hydrateApplicationImages();
      syncApplicationVisual(activeApplicationIndex, false);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        applicationAssetsReady = true;
        hydrateApplicationImages();
        syncApplicationVisual(activeApplicationIndex, false);
        observer.disconnect();
      },
      { rootMargin: "600px 0px" },
    );
    observer.observe(applicationShowcase);
  };

  // Initialization ------------------------------------------------------------

  activateApplication(activeApplicationIndex, { animate: false });
  setApplicationLanguage(applicationLang);
  setApplicationPhoneMode("home");
  initApplicationPreloading();
  window.addEventListener("load", initApplicationMotion, { once: true });
})();
