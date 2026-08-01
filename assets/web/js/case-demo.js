/**
 * Animated long-term memory case study.
 * Kept isolated so its timers and rendering state cannot leak into other demos.
 */

(() => {
  // Long-term memory case demo ------------------------------------------------

  const caseTyped = document.querySelector("[data-case-typed]");
  const caseSend = document.querySelector("[data-case-send]");
  const casePhone = document.querySelector(".case-phone");
  const caseChat = document.querySelector("[data-case-chat]");
  const caseUserMessage = document.querySelector("[data-case-user-message]");
  const caseUserText = document.querySelector("[data-case-user-text]");
  const caseThinking = document.querySelector("[data-case-thinking]");
  const caseReply = document.querySelector("[data-case-reply]");
  const caseReplyText = document.querySelector("[data-case-reply-text]");
  const caseFollowup = document.querySelector("[data-case-followup]");
  const caseFollowupText = document.querySelector("[data-case-followup-text]");
  const caseAlbumReply = document.querySelector("[data-case-album-reply]");
  const caseAlbumText = document.querySelector("[data-case-album-text]");
  const caseStatus = document.querySelector("[data-case-status]");
  const traceCards = Array.from(document.querySelectorAll("[data-trace-step]"));
  const caseCurrentThought = document.querySelector("[data-case-current-thought]");
  const memoryRoom = document.querySelector("[data-memory-room]");
  const roomBubble = document.querySelector(".room-bubble");
  const roomBubbleText = roomBubble ? roomBubble.querySelector(".room-bubble-text") : null;
  const caseCopy = {
    en: {
      prompt: "Could you find the photo from my daughter's 7th birthday?",
      reply: "Got it. Is this the one?",
      followup:
        "Yes. Do you remember other important photos from that year? Make an album for her birthday.",
      album: "OK, her album is ready.",
      send: "Send",
      sent: "Sent",
      status: {
        typing: "typing",
        ready: "ready",
        retrieving: "retrieving",
        result: "result found",
        album: "album ready",
      },
      thoughts: [
        {
          title: "Personalized KG",
          text: "Link family across years.",
          relationProof: [
            {
              year: "2026",
              img: "assets/web/case-user-2026.jpg",
              label: "User now",
              alt: "Current user portrait.",
            },
            {
              year: "2026",
              img: "assets/web/case-daughter-2026.jpg",
              label: "Daughter now",
              alt: "Current daughter portrait.",
            },
            {
              year: "2016",
              img: "assets/web/case-user-2016.jpg",
              label: "User 2016",
              alt: "Past user portrait.",
            },
            {
              year: "2016",
              img: "assets/web/case-daughter-2016.jpg",
              label: "Daughter 2016",
              alt: "Past daughter portrait.",
            },
          ],
          checks: [
            { text: "Find: current daughter", match: true },
            { text: "Find: past daughter", match: true },
            { text: "Link: user - daughter", match: true },
          ],
        },
        {
          title: "Multimodal Mem Bank",
          text: "Search school, trip, and birthday photo memories.",
          proof: {
            img: "assets/web/case-memory-bank.jpg",
            title: "Candidate memories",
            text: "school, trip, birthday",
            alt: "Candidate memories searched by MobileMem.",
          },
          checks: [
            { text: "Reject: Dau. School, not birthday" },
            { text: "Reject: Family Trip, no cake" },
            { text: "Keep: 7th Birthday candidate", match: true },
          ],
        },
        {
          title: "LTM Reasoning",
          text: "Use 2016 and 7th birthday to rank the birthday scene.",
          proof: {
            img: "assets/web/case-reasoning-match.jpg",
            title: "Cross-time match",
            text: "daughter + 2016 birthday",
            alt: "Cross-time reasoning match for the birthday scene.",
          },
          checks: [
            { text: "Match: daughter across years", match: true },
            { text: "Match: 2016 + 7th birthday", match: true },
            { text: "Match: family around cake", match: true },
          ],
        },
        {
          title: "Result",
          text: "Select the grounded photo for the final reply.",
          proof: {
            img: "assets/web/case-result-birthday.jpg",
            title: "Grounded photo",
            text: "family gathered around cake",
            alt: "Grounded birthday result photo.",
          },
        },
      ],
    },
    zh: {
      prompt: "帮我找一下我女儿 7 岁生日时拍的照片。",
      reply: "找到啦！您看是不是这张？",
      followup: "是的。你还记得那一年其他重要照片吗？帮她做一本生日相册。",
      album: "好的，她的相册已经准备好了。",
      send: "发送",
      sent: "已发送",
      status: {
        typing: "输入中",
        ready: "待发送",
        retrieving: "检索中",
        result: "已找到",
        album: "相册已生成",
      },
      thoughts: [
        {
          title: "个性化知识图谱",
          text: "先定位当前用户与女儿，再回溯到 2016 年家庭记忆中的用户与女儿。",
          relationProof: [
            {
              year: "2026",
              img: "assets/web/case-user-2026.jpg",
              label: "当前用户",
              alt: "当前用户照片。",
            },
            {
              year: "2026",
              img: "assets/web/case-daughter-2026.jpg",
              label: "当前女儿",
              alt: "当前女儿照片。",
            },
            {
              year: "2016",
              img: "assets/web/case-user-2016.jpg",
              label: "过去用户",
              alt: "过去用户照片。",
            },
            {
              year: "2016",
              img: "assets/web/case-daughter-2016.jpg",
              label: "过去女儿",
              alt: "过去女儿照片。",
            },
          ],
          checks: [
            { text: "找到：女儿当前照片", match: true },
            { text: "找到：女儿过去照片", match: true },
            { text: "确认：用户 - 女儿关系", match: true },
          ],
        },
        {
          title: "多模态记忆库",
          text: "检索学校、旅行、生日等候选照片记忆。",
          proof: {
            img: "assets/web/case-memory-bank.jpg",
            title: "候选记忆",
            text: "学校 / 旅行 / 生日",
            alt: "MobileMem 检索到的候选记忆。",
          },
          checks: [
            { text: "排除：女儿开学，不是生日" },
            { text: "排除：家庭出游，没有蛋糕" },
            { text: "保留：7 岁生日候选", match: true },
          ],
        },
        {
          title: "长程记忆推理",
          text: "结合 2016 年与 7 岁生日线索，对候选照片排序。",
          proof: {
            img: "assets/web/case-reasoning-match.jpg",
            title: "跨时间匹配",
            text: "女儿 + 2016 年生日",
            alt: "跨时间推理匹配生日场景。",
          },
          checks: [
            { text: "匹配：跨年份女儿身份", match: true },
            { text: "匹配：2016 年 + 7 岁生日", match: true },
            { text: "匹配：一家人围着蛋糕", match: true },
          ],
        },
        {
          title: "结果",
          text: "选择有依据的生日照片，准备回复用户。",
          proof: {
            img: "assets/web/case-result-birthday.jpg",
            title: "命中照片",
            text: "一家人围着生日蛋糕",
            alt: "命中的生日照片。",
          },
        },
      ],
    },
  };
  let caseLang = document.body.classList.contains("lang-zh") ? "zh" : "en";
  let phoneThoughts = caseCopy[caseLang].thoughts;
  const roomBubbleCopy = {
    en: ["Reading each identity cue", "Searching memories", "Matching time + cake", "Photo found"],
    zh: ["逐张读取身份线索", "检索记忆照片", "匹配时间与蛋糕", "已找到照片"],
  };
  const caseStageTimeline = [
    { id: "relations", hold: 7200 },
    { id: "retrieval", hold: 5400 },
    { id: "reasoning", hold: 3000 },
    { id: "result", hold: 820 },
  ];
  const caseAgentStepDuration = 145;
  const caseTimers = new Set();
  let caseRunId = 0;
  const roomAgentFootPoints = [
    { x: 50, y: 66 },
    { x: 51, y: 57 },
    { x: 24, y: 63 },
    { x: 76, y: 64 },
    { x: 52, y: 75 },
  ];
  const roomAgentPaths = [
    [roomAgentFootPoints[0]],
    [
      { x: 50, y: 66 },
      { x: 50.3, y: 63 },
      { x: 50.6, y: 60 },
      { x: 50.8, y: 58.5 },
      roomAgentFootPoints[1],
    ],
    [
      { x: 51, y: 57 },
      { x: 45, y: 59 },
      { x: 38, y: 61 },
      { x: 31, y: 63 },
      { x: 27, y: 63.5 },
      roomAgentFootPoints[2],
    ],
    [
      { x: 24, y: 63 },
      { x: 35, y: 65 },
      { x: 47, y: 66 },
      { x: 60, y: 66 },
      { x: 69, y: 65 },
      roomAgentFootPoints[3],
    ],
    [
      { x: 76, y: 64 },
      { x: 70, y: 67 },
      { x: 63, y: 70 },
      { x: 57, y: 73 },
      roomAgentFootPoints[4],
    ],
  ];

  Object.values(caseCopy)
    .flatMap((copy) => copy.thoughts)
    .forEach((thought) => {
      if (!thought.proof) return;
      const image = new Image();
      image.addEventListener("load", () => measureCasePhoneHeight(), {
        once: true,
      });
      image.src = thought.proof.img;
    });

  const clearCaseTimers = () => {
    caseTimers.forEach((timer) => window.clearTimeout(timer));
    caseTimers.clear();
  };

  const scheduleCase = (callback, delay, runId) => {
    const timer = window.setTimeout(() => {
      caseTimers.delete(timer);
      if (runId === caseRunId) callback();
    }, delay);
    caseTimers.add(timer);
  };

  const setCaseStatus = (text) => {
    if (caseStatus) caseStatus.textContent = text;
  };

  const scrollCaseChatToLatest = () => {
    if (!caseChat) return;
    window.requestAnimationFrame(() => {
      caseChat.scrollTo({ top: caseChat.scrollHeight, behavior: "smooth" });
    });
  };

  const setRoomAgentStep = (step) => {
    if (!memoryRoom) return;
    const safeStep = Math.max(0, Math.min(roomAgentFootPoints.length - 1, step));
    const point = roomAgentFootPoints[safeStep];
    memoryRoom.dataset.roomStep = String(safeStep);
    memoryRoom.style.setProperty("--agent-x", `${point.x}%`);
    memoryRoom.style.setProperty("--agent-y", `${point.y}%`);
  };

  const walkRoomAgentToStep = (step, runId, onArrive) => {
    if (!memoryRoom) {
      onArrive();
      return;
    }

    const safeStep = Math.max(0, Math.min(roomAgentPaths.length - 1, step));
    const path = roomAgentPaths[safeStep];
    memoryRoom.dataset.roomStep = "0";
    memoryRoom.dataset.roomMoving = String(safeStep);
    memoryRoom.dataset.caseSyncPhase = "moving";
    if (casePhone) casePhone.dataset.caseSyncPhase = "moving";
    if (roomBubble) roomBubble.classList.remove("is-pop");

    path.forEach((point, pointIndex) => {
      scheduleCase(
        () => {
          memoryRoom.style.setProperty("--agent-x", `${point.x}%`);
          memoryRoom.style.setProperty("--agent-y", `${point.y}%`);
        },
        pointIndex * caseAgentStepDuration,
        runId,
      );
    });

    scheduleCase(
      () => {
        memoryRoom.dataset.roomStep = String(safeStep);
        delete memoryRoom.dataset.roomMoving;
        onArrive();
      },
      path.length * caseAgentStepDuration,
      runId,
    );
  };

  const setRoomCasePhase = (phase) => {
    if (memoryRoom) memoryRoom.dataset.casePhase = phase;
  };

  const popRoomBubble = (text, runId, delay = 0) => {
    if (!roomBubble || !roomBubbleText) return;
    roomBubbleText.textContent = text;
    roomBubble.classList.remove("is-pop");
    scheduleCase(
      () => {
        void roomBubble.offsetWidth;
        roomBubble.classList.add("is-pop");
      },
      delay,
      runId,
    );
  };

  const currentCaseCopy = () => caseCopy[caseLang] || caseCopy.en;

  const renderPhoneThought = (index) => {
    const thought = phoneThoughts[index] || phoneThoughts[phoneThoughts.length - 1];
    const relationProof = thought.relationProof
      ? `<div class="case-relation-proof">${thought.relationProof.map((item) => `<div class="case-relation-card" data-year="${item.year}"><img src="${item.img}" alt="${item.alt}"><small>${item.label}</small></div>`).join("")}</div>`
      : "";
    const proof = thought.proof
      ? `<div class="case-thought-proof"><img src="${thought.proof.img}" alt="${thought.proof.alt}"><div><em>${thought.proof.title}</em><small>${thought.proof.text}</small></div></div>`
      : "";
    const checks = thought.checks
      ? `<div class="case-reject-list">${thought.checks.map((check) => `<span class="${check.match ? "is-match" : ""}">${check.text}</span>`).join("")}</div>`
      : "";
    return `<b>${thought.title}</b><span>${thought.text}</span>${relationProof}${proof}${checks}`;
  };

  const measureCasePhoneHeight = () => {
    const stage = document.querySelector(".case-stage");
    if (stage) stage.style.setProperty("--case-phone-h", "500px");
  };

  const resetCaseDemo = () => {
    const copy = currentCaseCopy();
    phoneThoughts = copy.thoughts;
    measureCasePhoneHeight();
    if (caseUserText) caseUserText.textContent = copy.prompt;
    if (caseReplyText) caseReplyText.textContent = copy.reply;
    if (caseFollowupText) caseFollowupText.textContent = copy.followup;
    if (caseAlbumText) caseAlbumText.textContent = copy.album;
    if (caseTyped) caseTyped.innerHTML = '<span class="case-cursor"></span>';
    if (caseSend) {
      caseSend.classList.remove("is-ready", "is-sent");
      caseSend.textContent = copy.send;
    }
    if (caseUserMessage) caseUserMessage.classList.remove("is-visible");
    if (caseChat) caseChat.classList.remove("is-active");
    if (caseChat) caseChat.scrollTop = 0;
    if (caseThinking) caseThinking.classList.remove("is-visible", "is-collapsing");
    if (caseReply) caseReply.classList.remove("is-visible");
    if (caseFollowup) caseFollowup.classList.remove("is-visible");
    if (caseAlbumReply) caseAlbumReply.classList.remove("is-visible");
    traceCards.forEach((card) => card.classList.remove("is-active", "is-done"));
    if (caseCurrentThought) {
      caseCurrentThought.classList.remove("is-changing");
      caseCurrentThought.dataset.step = "1";
      caseCurrentThought.innerHTML = renderPhoneThought(0);
    }
    if (casePhone) casePhone.dataset.caseSyncStep = "0";
    if (casePhone) casePhone.dataset.caseSyncPhase = "idle";
    if (memoryRoom) memoryRoom.dataset.caseSyncPhase = "idle";
    setRoomAgentStep(0);
    setRoomCasePhase("search");
    if (roomBubble) roomBubble.classList.remove("is-pop");
    setCaseStatus(copy.status.typing);
  };

  const runCaseDemo = () => {
    if (
      !caseTyped ||
      !caseSend ||
      !caseChat ||
      !caseUserMessage ||
      !caseThinking ||
      !caseReply ||
      !caseCurrentThought
    )
      return;
    clearCaseTimers();
    caseRunId += 1;
    const runId = caseRunId;
    resetCaseDemo();
    let charIndex = 0;
    const copy = currentCaseCopy();
    const casePrompt = copy.prompt;

    const typeNext = () => {
      if (charIndex < casePrompt.length) {
        const text = casePrompt.slice(0, charIndex + 1);
        caseTyped.innerHTML = `${text}<span class="case-cursor"></span>`;
        charIndex += 1;
        scheduleCase(typeNext, 28 + Math.random() * 28, runId);
        return;
      }

      caseTyped.textContent = casePrompt;
      caseSend.classList.add("is-ready");
      setCaseStatus(copy.status.ready);
      scheduleCase(sendPrompt, 620, runId);
    };

    const sendPrompt = () => {
      caseSend.classList.add("is-sent");
      caseSend.textContent = copy.sent;
      caseTyped.innerHTML = "";
      caseChat.classList.add("is-active");
      caseUserMessage.classList.add("is-visible");
      scrollCaseChatToLatest();
      setCaseStatus(copy.status.retrieving);
      scheduleCase(
        () => {
          activateTrace(0);
        },
        420,
        runId,
      );
    };

    const setPhoneThought = (index) => {
      const thought = phoneThoughts[index] || phoneThoughts[phoneThoughts.length - 1];
      caseCurrentThought.dataset.step = String(index + 1);
      caseCurrentThought.classList.add("is-changing");
      caseCurrentThought.innerHTML = renderPhoneThought(index);
      if (casePhone) casePhone.dataset.caseSyncStep = String(index + 1);
      scheduleCase(
        () => {
          caseCurrentThought.classList.remove("is-changing");
        },
        420,
        runId,
      );
    };

    const activateTrace = (index) => {
      walkRoomAgentToStep(index + 1, runId, () => {
        const stage = caseStageTimeline[index] || caseStageTimeline.at(-1);
        if (casePhone) casePhone.dataset.caseSyncPhase = stage.id;
        if (memoryRoom) memoryRoom.dataset.caseSyncPhase = stage.id;
        traceCards.forEach((card, cardIndex) => {
          card.classList.toggle("is-active", cardIndex === index);
          card.classList.toggle("is-done", cardIndex < index);
        });
        if (index === 0) {
          caseThinking.classList.add("is-visible");
          scrollCaseChatToLatest();
        }
        setPhoneThought(index);

        if (roomBubble && roomBubbleText && phoneThoughts[index]) {
          const roomTexts = roomBubbleCopy[caseLang] || roomBubbleCopy.en;
          popRoomBubble(roomTexts[index] || phoneThoughts[index].text, runId);
        }

        if (index < phoneThoughts.length - 1) {
          scheduleCase(() => activateTrace(index + 1), stage.hold, runId);
          return;
        }

        scheduleCase(
          () => {
            traceCards.forEach((card) => {
              card.classList.remove("is-active");
              card.classList.add("is-done");
            });
            caseThinking.classList.add("is-collapsing");
            setCaseStatus(copy.status.result);
            scheduleCase(
              () => {
                caseThinking.classList.remove("is-visible", "is-collapsing");
                caseReply.classList.add("is-visible");
                scrollCaseChatToLatest();
                scheduleCase(
                  () => {
                    if (caseFollowup) {
                      caseFollowup.classList.add("is-visible");
                      scrollCaseChatToLatest();
                    }
                    scheduleCase(
                      () => {
                        const albumRoomTexts =
                          caseLang === "zh"
                            ? ["整理 2016 年重要照片", "生日相册已完成"]
                            : ["Collecting 2016 memories", "Album ready"];
                        popRoomBubble(albumRoomTexts[0], runId);
                        scheduleCase(
                          () => {
                            setCaseStatus(copy.status.album);
                            setRoomCasePhase("album");
                            popRoomBubble(albumRoomTexts[1], runId);
                            if (caseAlbumReply) {
                              caseAlbumReply.classList.add("is-visible");
                              scrollCaseChatToLatest();
                            }
                            scheduleCase(runCaseDemo, 5200, runId);
                          },
                          850,
                          runId,
                        );
                      },
                      1250,
                      runId,
                    );
                  },
                  950,
                  runId,
                );
              },
              320,
              runId,
            );
          },
          stage.hold,
          runId,
        );
      });
    };

    typeNext();
  };

  const setCaseLanguage = (lang) => {
    caseLang = lang === "zh" ? "zh" : "en";
    runCaseDemo();
  };

  window.addEventListener("mobilemem:languagechange", (event) => {
    const nextLang = event.detail?.lang === "zh" ? "zh" : "en";
    if (nextLang !== caseLang) setCaseLanguage(nextLang);
  });

  runCaseDemo();
})();
