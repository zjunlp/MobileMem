/**
 * Static configuration for the interactive MobileMem sample browser.
 * Shared by the browser controller and the image-manifest tooling.
 */

(() => {
  const users = ["uid0", "uid1", "uid2", "uid10", "uid11", "uid12"];
  const categories = [
    "group_chat",
    "event",
    "person",
    "scenery",
    "book",
    "music",
    "shopping",
    "money",
    "ticket",
    "video",
    "friend",
    "group_chat_members",
  ];

  const typeCopy = {
    group_chat: {
      zh: "群聊",
      en: "Group chat",
      title: { zh: "群聊记录", en: "Group chat records" },
    },
    event: {
      zh: "事件",
      en: "Events",
      title: { zh: "事件场景", en: "Event scenes" },
    },
    person: {
      zh: "人物",
      en: "Person",
      title: { zh: "人物参考", en: "Persona reference" },
    },
    scenery: {
      zh: "场景",
      en: "Scenes",
      title: { zh: "生活场景", en: "Life scenes" },
    },
    book: {
      zh: "阅读",
      en: "Books",
      title: { zh: "阅读记录", en: "Book records" },
    },
    music: {
      zh: "音乐",
      en: "Music",
      title: { zh: "音乐记录", en: "Music records" },
    },
    shopping: {
      zh: "购物",
      en: "Shopping",
      title: { zh: "购物记录", en: "Shopping records" },
    },
    money: {
      zh: "账单",
      en: "Bills",
      title: { zh: "账单记录", en: "Payment records" },
    },
    ticket: {
      zh: "票务",
      en: "Tickets",
      title: { zh: "票务记录", en: "Ticket records" },
    },
    video: {
      zh: "视频",
      en: "Video",
      title: { zh: "视频记录", en: "Video records" },
    },
    friend: {
      zh: "动态",
      en: "Posts",
      title: { zh: "朋友圈记录", en: "Social posts" },
    },
    group_chat_members: {
      zh: "群成员",
      en: "Members",
      title: { zh: "群成员头像", en: "Group member portraits" },
    },
  };

  const categoryCounts = {
    uid0: {
      group_chat: 834,
      event: 208,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 21,
      ticket: 20,
      video: 30,
      friend: 20,
      group_chat_members: 16,
    },
    uid1: {
      group_chat: 917,
      event: 229,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 20,
      ticket: 22,
      video: 28,
      friend: 20,
      group_chat_members: 15,
    },
    uid2: {
      group_chat: 967,
      event: 234,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 20,
      ticket: 19,
      video: 29,
      friend: 20,
      group_chat_members: 15,
    },
    uid10: {
      group_chat: 789,
      event: 215,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 20,
      ticket: 22,
      video: 30,
      friend: 20,
      group_chat_members: 15,
    },
    uid11: {
      group_chat: 760,
      event: 221,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 20,
      ticket: 20,
      video: 30,
      friend: 20,
      group_chat_members: 15,
    },
    uid12: {
      group_chat: 806,
      event: 202,
      person: 5,
      scenery: 18,
      book: 30,
      music: 30,
      shopping: 30,
      money: 20,
      ticket: 17,
      video: 30,
      friend: 20,
      group_chat_members: 15,
    },
  };

  const identityLabels = {
    uid0: {
      person: ["王景川", "蒋立新", "蔡雪宁", "郝志强", "穆长安"],
      group_chat_members: ["蒋立新", "蔡雪宁", "郝志强", "穆长安", "敖晨露"],
    },
    uid1: {
      person: ["李曼青", "穆佳悦", "崔俊豪", "聂雨晴", "靳若楠"],
      group_chat_members: ["穆佳悦", "李春霞", "聂雨晴", "靳若楠", "李建东"],
    },
    uid2: {
      person: ["赵雨棠", "梅晓彤", "甘晨曦", "郝心怡", "蒋立恒"],
      group_chat_members: ["梅晓彤", "甘晨曦", "郝心怡", "蒋立恒", "赵慧敏"],
    },
    uid10: {
      person: ["Michael Carter", "Liam O’Brien", "Alex Rivera", "Rachel Stein", "Jason Miller"],
      group_chat_members: [
        "Liam O’Brien",
        "Alex Rivera",
        "Rachel Stein",
        "Jason Miller",
        "Kevin Lee",
      ],
    },
    uid11: {
      person: [
        "Emily Rose Carter",
        "Grace Miller",
        "Michael Carter",
        "Noah Baker",
        "Rebecca Carter",
      ],
      group_chat_members: [
        "Madison Clark",
        "Michael Carter",
        "Noah Baker",
        "Rebecca Carter",
        "Sophie Carter",
      ],
    },
    uid12: {
      person: [
        "Melissa Ann Carter",
        "Erica Morales",
        "Justin Ward",
        "Tara Mitchell",
        "Sandra Lopez",
      ],
      group_chat_members: [
        "Erica Morales",
        "Justin Ward",
        "Tara Mitchell",
        "Sandra Lopez",
        "Paula Jenkins",
      ],
    },
  };

  const eventLabels = {
    uid0: ["元旦年度规划", "婚礼方向长谈", "单位工作计划定稿", "春节前商场采购", "春节前加班餐"],
    uid1: ["元旦跑单目标", "给家人报平安", "夜间饺子外卖", "冬季车辆安全检查", "春节前在家囤干粮"],
    uid2: ["宿舍制定新年规划", "元旦宿舍小聚", "图书馆碰头", "课程与见习安排", "每日时间块设计"],
    uid10: [
      "New Year reflection",
      "Q1 roadmap lunch",
      "ML course research",
      "Cramped apartment",
      "ML course discussion",
    ],
    uid11: [
      "New Year goals",
      "Semester stress dinner",
      "Club workload",
      "Soccer conditioning",
      "MLK Day volunteering",
    ],
    uid12: [
      "Quiet New Year shift",
      "Realistic New Year goals",
      "Rural burnout book",
      "Comfort Tex-Mex",
      "Car maintenance",
    ],
  };

  const curatedTypes = new Set([
    "group_chat",
    "event",
    "book",
    "music",
    "shopping",
    "money",
    "ticket",
    "video",
    "friend",
  ]);
  const fullyCuratedUsers = new Set(["uid2", "uid12"]);

  const resolveAssetPath = (uid, type, sampleNumber = 1) => {
    const portraitOverride = uid === "uid11" && ["person", "group_chat_members"].includes(type);
    const directory =
      curatedTypes.has(type) || fullyCuratedUsers.has(uid) || portraitOverride
        ? "assets/web/memweb/curated"
        : "assets/web/memweb";
    return `${directory}/${uid}-${type}-${String(sampleNumber).padStart(2, "0")}.png`;
  };

  globalThis.MobileMemApplicationData = Object.freeze({
    users,
    categories,
    typeCopy,
    categoryCounts,
    identityLabels,
    eventLabels,
    previewCount: 5,
    resolveAssetPath,
  });
})();
