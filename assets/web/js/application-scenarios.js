/** Application scenario accordion and matching dialogue trajectories. */

(() => {
  const textTurn = (role, zh, en) => ({ role, text: { zh, en } });
  const imageTurn = (role, srcZh, srcEn, altZh, altEn) => ({
    role,
    src: { zh: srcZh, en: srcEn },
    alt: { zh: altZh, en: altEn },
  });

  const scenarios = [
    {
      title: { zh: "健康管理与用药提醒", en: "Health and Medication" },
      avatar: {
        zh: "assets/web/memweb/generated/scenarios/health-user-avatar-v2.webp",
        en: "assets/web/memweb/generated/scenarios/health-user-avatar-v2.webp",
      },
      messages: [
        textTurn("user", "今天早上起床后有点头晕。我以前对什么药过敏？现在吃的药里有吗？", "I felt dizzy after getting up this morning. What was I allergic to, and is it in my current medication?"),
        textTurn("ai", "2019 年体检报告和健康档案都记录了青霉素类过敏；上月最后一个周五的复诊笔记更新过药单。我先核对那次复诊。", "Your 2019 examination report and health record both list a penicillin allergy. Your medication list changed at the follow-up visit on the final Friday of last month, so I will start there."),
        textTurn("user", "这是那次复诊的照片，医生当时重新看了我的血压记录。", "This is the follow-up visit. The doctor reviewed my blood-pressure log then."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/health-followup-event-v2.webp",
          "assets/web/memweb/generated/scenarios/health-followup-event-v2.webp",
          "用户在门诊复诊并与医生核对用药",
          "The user reviews medication with a doctor during a follow-up visit",
        ),
        textTurn("ai", "照片与日历中的复诊时间一致；同日相册里还有处方照片，笔记记录为“停用旧药，新增一项，剂量不变”。", "The photo matches the Calendar visit. Photos also contains a same-day prescription, while Notes says: stop the old medicine, add one new item, and keep the other doses unchanged."),
        textTurn("user", "我记不清新加的是哪一盒了。", "I cannot remember which box was newly added."),
        textTurn("ai", "为避免只凭处方转写判断，请把现在实际在吃的药盒和服药表一起拍给我。", "To avoid relying only on the transcribed prescription, please photograph the boxes you actually take together with your medication schedule."),
        textTurn("user", "我把四种药和服药表都摆出来了，这是我今天早上实际服用的。", "I laid out all four medicines with my schedule. These are what I actually took this morning."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/health-medication-check-event-v1.webp",
          "assets/web/memweb/generated/scenarios/health-medication-check-event-v1.webp",
          "桌面上的当前药盒、药板与服药表",
          "Current medicine boxes, blister packs, and medication schedule on a table",
        ),
        textTurn("ai", "药盒照片与处方中的四项一致。没有发现同名青霉素成分，但新加的那项属于需要医生复核交叉过敏风险的相关药类。", "The four boxes match the prescription. The exact penicillin allergen is not listed, but the newly added item belongs to a related class whose cross-allergy risk needs clinician review."),
        textTurn("user", "我之前在浏览器里查过禁忌，里面是不是也提醒过这个？", "Did the contraindication page I viewed before mention this too?"),
        textTurn("ai", "是。三周前保存的浏览记录提醒有严重药物过敏史的人先咨询医生，但它是通用说明，不能替代医生对你这份药单的判断。", "Yes. A browser record saved three weeks ago advises people with serious drug allergies to consult a clinician first, but that general guidance cannot replace review of your specific medication list."),
        textTurn("user", "我刚才也量了血压和血糖，这是现场照片。", "I also checked my blood pressure and glucose just now. Here is the photo."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/health-home-vitals-event-v1.webp",
          "assets/web/memweb/generated/scenarios/health-home-vitals-event-v1.webp",
          "用户清晨在家测量血压并记录健康数据",
          "The user records blood pressure and health data at home in the morning",
        ),
        textTurn("ai", "照片时间与今天的健康记录一致。与最近七次居家记录相比没有明显突变，但这仍不能说明头晕一定由哪一种药引起。", "The photo timestamp matches today's health entry. The readings do not show a clear departure from your last seven home records, but that still does not identify which medicine, if any, caused the dizziness."),
        textTurn("user", "那我是不是先把新药停一天？", "Should I stop the new medicine for a day?"),
        textTurn("ai", "不要自行停药、减量或补服。现在能确认的是过敏史与新药类别需要复核，头晕原因还不能由这些记录确定。", "Do not stop, reduce, or make up a dose on your own. The records establish that your allergy history and the new drug class need review, but they do not establish the cause of the dizziness."),
        textTurn("user", "什么情况需要马上去急诊？", "What symptoms mean I should seek emergency care immediately?"),
        textTurn("ai", "若出现呼吸困难、面唇或舌头肿胀、全身风团、胸闷、持续呕吐或晕厥，请立即急诊；不要等待线上回复。", "Seek emergency care immediately for trouble breathing, swelling of the face, lips, or tongue, widespread hives, chest tightness, persistent vomiting, or fainting. Do not wait for an online reply."),
        textTurn("user", "现在没有这些，就是轻微头晕，坐下后好一些。", "I have none of those. It is mild dizziness and improved after I sat down."),
        textTurn("ai", "先坐稳、补充少量水分，今天避免独自开车；在下一次服药前联系开药医生或药师，说明过敏史和今早症状。", "Stay seated, drink a little water, and avoid driving alone today. Contact the prescribing clinician or pharmacist before the next dose and report the allergy history and this morning's symptoms."),
        textTurn("user", "帮我把要发给医生的材料整理好。", "Prepare the material I should send the doctor."),
        textTurn("ai", "我已汇总过敏记录、既往反应、复诊日期、同日处方、四种当前药物、今早服药时间，以及最近七次血压血糖记录。", "I compiled the allergy record, previous reaction, visit date, same-day prescription, four current medicines, this morning's dose time, and the last seven blood-pressure and glucose entries."),
        textTurn("user", "药名、剂量和每天什么时候吃也要写清楚。", "Include the medicine names, doses, and daily timing clearly."),
        textTurn("ai", "已逐项写入，并把新加的药标为“请医生确认交叉过敏风险”，没有替你修改任何剂量。", "Each item now includes its dose and schedule. The new medicine is flagged for clinician confirmation of cross-allergy risk, with no dose changes made on your behalf."),
        textTurn("user", "下次复诊是什么时候？今天联系医生也提醒我。", "When is my next follow-up? Remind me to contact the doctor today too."),
        textTurn("ai", "日历显示下周二 09:30 复诊。我已设置今天 09:00 联系门诊、复诊前一天 20:00 准备药盒和记录两项提醒。", "Calendar shows a follow-up next Tuesday at 09:30. I set reminders to contact the clinic today at 09:00 and prepare the medicine boxes and records at 20:00 the night before the visit."),
        textTurn("user", "给我一句能直接发给医生的话。", "Give me a message I can send the doctor directly."),
        textTurn("ai", "“我有青霉素类过敏史，上月复诊后新增了一种药，今早服药后轻微头晕，目前无呼吸困难或肿胀。附件是当前药单、处方和近期记录，请帮我确认是否需要调整。”", "‘I have a penicillin allergy history and started one new medicine after last month's follow-up. I had mild dizziness after this morning's dose, with no breathing difficulty or swelling. I have attached my current list, prescription, and recent readings. Please advise whether any adjustment is needed.’"),
        textTurn("user", "好，我现在就联系门诊，不自己停药。", "Good. I will contact the clinic now and will not stop the medicine on my own."),
      ],
    },
    {
      title: { zh: "旅行行程规划", en: "Travel Itinerary Planning" },
      avatar: {
        zh: "assets/web/memweb/uid0-person-01.webp",
        en: "assets/web/memweb/uid0-person-01.webp",
      },
      messages: [
        textTurn("user", "根据我这段时间收藏的内容，成都周边两天怎么安排比较好？", "Based on everything I have saved recently, what is a good two-day route around Chengdu?"),
        textTurn("ai", "你的收藏主要集中在川西山景；交通搜索偏向自驾或包车，住宿记录偏好可取消、停车方便、少换乘。", "Your saves concentrate on western Sichuan scenery. Transport searches favor driving or a hired car, while lodging history favors free cancellation, easy parking, and fewer transfers."),
        textTurn("user", "这张是我最想去的感觉，不想把两天都花在市区。", "This is closest to what I want. I do not want to spend both days in the city."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/travel-event-v1.webp",
          "assets/web/memweb/generated/scenarios/travel-event-v1.webp",
          "收藏的川西山景",
          "Saved mountain scenery in western Sichuan",
        ),
        textTurn("ai", "这张照片的山口、公路和雪峰与你反复收藏的巴朗山路线一致。九寨沟虽然也收藏过，但两天往返会把大部分时间耗在路上，因此不纳入。", "The pass, road, and snow peaks match the Balang Mountain route you saved repeatedly. Jiuzhaigou also appears in your bookmarks, but a two-day return trip would spend most of the time in transit, so I excluded it."),
        textTurn("user", "好，那就按川西方向。第一天具体怎么走？", "All right, use the western Sichuan direction. What exactly should day one look like?"),
        textTurn("ai", "07:30 从成都出发，上午到都江堰停留约两小时；午后沿都汶高速到映秀，参观后在镇上吃晚饭并入住。", "Leave Chengdu at 07:30, spend about two hours in Dujiangyan, then follow the Dujiangyan-Wenchuan Expressway to Yingxiu in the afternoon. Visit the town, have dinner there, and stay overnight."),
        textTurn("user", "这样开车会不会太久？我不想赶夜路。", "Is that too much driving? I do not want to drive after dark."),
        textTurn("ai", "按你过去自驾记录的节奏，第一天约三小时实际驾驶，分成两段；17:30 前能到住宿地，不需要夜间翻山。", "At the pace shown in your past road trips, day one involves about three hours of driving split into two legs. You can reach the stay before 17:30 without crossing mountain roads at night."),
        textTurn("user", "我收藏过这种映秀附近的小住处，你看合适吗？", "I saved this kind of small place near Yingxiu. Does it fit?"),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/travel-yingxiu-stay-event-v1.webp",
          "assets/web/memweb/generated/scenarios/travel-yingxiu-stay-event-v1.webp",
          "映秀附近可停车的山间住宿",
          "A mountain stay near Yingxiu with parking",
        ),
        textTurn("ai", "合适。照片显示门口可停车、行李搬运距离短，也符合你之前选择小型住处而非大型度假酒店的习惯。预订时优先选可免费取消的房型。", "It fits. The photo shows parking at the entrance and a short carry for luggage, matching your preference for small stays over large resorts. Choose a room with free cancellation."),
        textTurn("user", "如果都江堰玩得晚，到映秀还有饭吃吗？", "If I leave Dujiangyan late, will I still find dinner in Yingxiu?"),
        textTurn("ai", "建议最迟 15:00 离开都江堰，18:00 左右在映秀用餐。若延误，就在都江堰提前吃饭，不把晚餐押在深夜到达后。", "Leave Dujiangyan by 15:00 and aim to eat in Yingxiu around 18:00. If delayed, eat in Dujiangyan instead of depending on a late arrival."),
        textTurn("user", "第二天怎么安排，才能看到四姑娘山又不太累？", "How should I plan day two to see Mount Siguniang without making it exhausting?"),
        textTurn("ai", "07:00 从映秀出发，经卧龙前往巴朗山口，在安全观景点停留，不继续深入长坪沟；午后原路返程，预计 18:30 前回到成都。", "Leave Yingxiu at 07:00, pass through Wolong to Balang Pass, and stop only at safe viewpoints rather than continuing into Changping Valley. Return the same way and reach Chengdu before about 18:30."),
        textTurn("user", "我以前到高海拔会头疼，行程里要留余量。", "I have had headaches at high altitude before, so the plan needs some margin."),
        textTurn("ai", "已把山口停留控制在 30 分钟内，不安排剧烈活动；若头痛加重、恶心或明显乏力就立即下降，不为打卡继续上行。", "I limited the pass stop to 30 minutes with no strenuous activity. If headache worsens or nausea or marked fatigue appears, descend immediately rather than continuing for a photo stop."),
        textTurn("user", "第二天如果下雨或者山口起雾怎么办？", "What if it rains or the pass is foggy on day two?"),
        textTurn("ai", "出发前一晚检查天气与路况；若能见度差或道路管制，就取消巴朗山，不临时冒险。你收藏里还有一条卧龙低海拔备选。", "Check weather and road conditions the night before. If visibility is poor or restrictions are in place, cancel Balang Mountain rather than improvising. Your saves include a lower-altitude Wolong fallback."),
        textTurn("user", "是这种雨雾路况，我不想在这种天气上山口。", "This is the kind of rainy, foggy road I mean. I do not want to climb to the pass in this weather."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/travel-wolong-weather-event-v1.webp",
          "assets/web/memweb/generated/scenarios/travel-wolong-weather-event-v1.webp",
          "雨雾中的卧龙低海拔山路",
          "A lower-altitude Wolong mountain road in rain and mist",
        ),
        textTurn("ai", "这种条件下直接启用备选：在卧龙低海拔路段停留，缩短户外步行，午后提前返蓉。照片里的湿滑路面也说明需要增加制动距离。", "In these conditions, use the fallback immediately: stay on lower-altitude Wolong roads, shorten outdoor walks, and return to Chengdu earlier. The wet road in the photo also calls for greater braking distance."),
        textTurn("user", "两天需要带什么？别给我一长串用不上的东西。", "What do I actually need for two days? Do not give me a huge generic packing list."),
        textTurn("ai", "只保留八项：身份证件、充电宝、离线地图、轻薄保暖层、雨具、防晒、常用药和少量饮水；住宿只住一晚，不需要大行李箱。", "Keep it to eight items: identification, power bank, offline map, light warm layer, rain gear, sun protection, regular medicine, and some water. One overnight stay does not require a large suitcase."),
        textTurn("user", "几点出发最合适？路线也帮我离线保存。", "What departure time works best? Save the route offline too."),
        textTurn("ai", "第一天 07:30、第二天 07:00 出发最稳妥。我已保存成都—都江堰—映秀和映秀—卧龙—巴朗山两段离线路线。", "The most reliable departure times are 07:30 on day one and 07:00 on day two. I saved offline routes for Chengdu-Dujiangyan-Yingxiu and Yingxiu-Wolong-Balang Mountain."),
        textTurn("user", "把最终行程、住宿要求和天气备选放到同一个清单里，并提醒我检查路况。", "Put the final route, lodging requirements, and weather fallback in one checklist, and remind me to check road conditions."),
        textTurn("ai", "清单已保存：主方案、卧龙备选、可取消住宿、车辆与停车要求、八项行李都已列入；出发前一晚 20:00 会提醒检查天气和道路通告。", "The checklist is saved with the main route, Wolong fallback, cancellable stay, vehicle and parking requirements, and eight packing items. A reminder at 20:00 the night before will prompt a weather and road-status check."),
        textTurn("user", "这个节奏可以，既看山景也不用一直赶路。", "This pace works. I can see the mountains without rushing all day."),
      ],
    },
    {
      title: { zh: "追剧记录对比长评", en: "Drama Tracking Review" },
      avatar: {
        zh: "assets/web/memweb/uid0-person-03.webp",
        en: "assets/web/memweb/uid0-person-03.webp",
      },
      messages: [
        textTurn("user", "根据我过去的追剧记录，把和这部新剧有关的内容整理出来，写一篇对比长评，不要在线搜索。", "Use my past viewing records to organize material related to this new drama and write a comparative long review without searching online."),
        textTurn("ai", "我已在多年的观剧笔记、相册截图和历史评论中找到三部主题相近的作品，其中一部在你的笔记里被反复引用。", "I found three related works across years of viewing notes, photo screenshots, and past reviews. One of them is cited repeatedly in your archive."),
        textTurn("user", "这是新剧里让我突然觉得似曾相识的一幕。", "This scene from the new drama suddenly felt familiar."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/drama-event-v1.webp",
          "assets/web/memweb/generated/scenarios/drama-event-v1.webp",
          "新剧中的人物对话画面",
          "A character dialogue scene from the new drama",
        ),
        textTurn("ai", "门框把两个人分在两个空间里，与 2019 年 11 月家庭剧观后记中的旧截图构图相似，也对应你写过的“人物不说破，镜头替他们说完”。", "The doorframe separates the two characters into distinct spaces, matching a screenshot in your November 2019 family-drama review and your line: ‘The characters leave it unsaid; the camera finishes it for them.’"),
        textTurn("user", "把当时的原话和截图依据都找出来。", "Find the original wording and the screenshot evidence."),
        textTurn("ai", "已定位两句原话和四张截图：门框对话、餐桌沉默、走廊回望、结尾空镜。每一项都保留原笔记日期。", "I located two original quotations and four screenshots: the doorway exchange, dinner-table silence, hallway glance, and final empty shot. Each keeps its original note date."),
        textTurn("user", "这是我昨晚边看边写的笔记，字有点乱。", "These are the notes I wrote while watching last night. The handwriting is messy."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/drama-viewing-notes-event-v1.webp",
          "assets/web/memweb/generated/scenarios/drama-viewing-notes-event-v1.webp",
          "新剧播放画面、手写观剧笔记与保存截图",
          "The new drama, handwritten viewing notes, and saved scene prints",
        ),
        textTurn("ai", "这页笔记与昨晚的播放记录时间一致。你重复写了三个词：克制、错位、没有说出口；它们可以作为长评的个人观察主线。", "The note timestamp aligns with last night's viewing record. Three ideas recur: restraint, misalignment, and what remains unsaid. They can form the personal thread of the review."),
        textTurn("user", "先比较叙事，不要只说“都很像”。", "Start with narrative. Do not merely say the two works are similar."),
        textTurn("ai", "共同点是都把关键事实延迟到后半段；区别是旧作靠日常细节慢慢改变观众判断，新剧则用两次集中反转重新解释前面的冲突。", "Both delay crucial information until the latter half. The older work gradually changes the viewer's judgment through daily details, while the new one uses two concentrated reversals to reinterpret earlier conflict."),
        textTurn("user", "人物关系呢？我觉得新剧更直接。", "What about the relationships? The new drama feels more direct."),
        textTurn("ai", "你的感觉与笔记一致。旧作让亲子矛盾通过沉默和回避累积；新剧让人物更早正面争执，因此情绪更强，但留白更少。", "That matches your notes. The older work accumulates parent-child conflict through silence and avoidance; the new drama brings confrontation forward, making emotion stronger but leaving less ambiguity."),
        textTurn("user", "镜头和声音也要单独比较。", "Compare image and sound separately too."),
        textTurn("ai", "旧作多用固定长镜头和室内环境声维持压力；新剧用更快的正反打、门响和脚步声推动冲突。门框构图相似，但节奏功能不同。", "The older work uses static long takes and interior ambience to sustain pressure. The new drama uses faster shot-reverse-shot editing, door sounds, and footsteps to propel conflict. The doorway framing is similar, but its rhythmic function differs."),
        textTurn("user", "不要把我的语气改成那种很空的专业影评。", "Do not turn my voice into an empty professional-review style."),
        textTurn("ai", "我会保留你笔记里的短句和犹豫，例如“这里太满了，反而没让我难受”，只在后面补充证据和比较，不替你拔高。", "I will keep your short, tentative phrasing, such as ‘This scene is so full that it affects me less,’ and add evidence and comparison without inflating the claim."),
        textTurn("user", "我把以前整理截图的桌面也拍了，看看能不能串起来。", "I also photographed the desk where I organized older screenshots. See whether they connect."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/drama-archive-comparison-event-v1.webp",
          "assets/web/memweb/generated/scenarios/drama-archive-comparison-event-v1.webp",
          "跨年份观剧笔记、旧截图与新剧画面的对照",
          "A cross-year comparison of viewing notes, older screenshots, and the new drama",
        ),
        textTurn("ai", "可以。桌面中的三册笔记分别对应 2019、2021 和 2023 年，截图共同出现“隔着空间说话”的构图，形成了可追溯的跨年份母题。", "Yes. The three notebooks correspond to 2019, 2021, and 2023. Their screenshots repeatedly stage conversation across separated spaces, creating a traceable cross-year motif."),
        textTurn("user", "也要写新剧哪里做得不够，不要因为我刚看完就只夸。", "Include where the new drama falls short. Do not praise it simply because I just finished it."),
        textTurn("ai", "会写两点：第三幕把原本含蓄的动机解释得过满；配角在关键转折后没有获得足够收束。这两点都来自你昨晚的即时笔记。", "I will include two weaknesses: the third act overexplains motives that were initially subtle, and supporting characters receive too little closure after the main turn. Both points come from your immediate notes last night."),
        textTurn("user", "每个主要观点都标清楚来自哪篇笔记或哪张图。", "Mark which note or image supports every major point."),
        textTurn("ai", "正文将使用日期脚注和截图编号：叙事部分对应三篇旧笔记，人物部分对应昨晚笔记，视听部分对应六张新旧截图。", "The draft will use dated footnotes and screenshot numbers: three older notes for narrative, last night's notes for character analysis, and six old and new screenshots for image and sound."),
        textTurn("user", "先告诉我最后会按什么结构写。", "Tell me the final structure before you finish it."),
        textTurn("ai", "五部分：熟悉感从何而来、叙事机制、人物关系、镜头与声音、个人观看史中的重复母题；结尾单列新剧的优点与不足。", "Five sections: where the familiarity begins, narrative mechanism, character relationships, image and sound, and recurring motifs in your viewing history, followed by a separate assessment of the new drama's strengths and weaknesses."),
        textTurn("user", "就按这个写，结尾回答为什么是它让我想起那些旧作品。", "Use that structure, and end by explaining why this particular drama brought those older works back to me."),
        textTurn("ai", "长评已生成并保存到笔记。结论是：相似的不只是剧情，而是你长期关注的“被空间隔开的亲密关系”和“延迟和解”；新剧用更直接的声音与剪辑重新触发了这段观看记忆。", "The long review is generated and saved to Notes. Its conclusion is that the resemblance lies not only in plot but in your long-standing interest in intimacy divided by space and delayed reconciliation. The new drama reactivated that viewing memory through more direct sound and editing."),
        textTurn("user", "这个结论像我自己的话，来源也够清楚，可以保留。", "That conclusion sounds like me, and the sources are clear enough. Keep it."),
      ],
    },
    {
      title: { zh: "半年工作复盘", en: "Six-Month Work Review" },
      avatar: {
        zh: "assets/web/memweb/generated/scenarios/work-user-avatar-v2.webp",
        en: "assets/web/memweb/generated/scenarios/work-user-avatar-v2.webp",
      },
      messages: [
        textTurn("user", "帮我复盘过去半年的工作。结合上次技术分享，梳理我主要补了什么知识、工作卡在哪里。", "Review my work from the past six months. Use my last technical sharing session to identify what I learned and where work kept stalling."),
        textTurn("ai", "我正在对齐日历会议和里程碑、文档版本、零散笔记，以及屏幕记忆中的技术文章主题。当前记录显示是一条主项目线和三项短期支持任务。", "I am aligning Calendar meetings and milestones, document versions, fragmented notes, and technical-article themes from screen memory. The record shows one main project and three short support tasks."),
        textTurn("user", "这是其中一次连续改方案时拍的，桌上都是那周的版本。", "This was taken during one intensive proposal revision. The desk held that week's versions."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/work-review-event-v2.webp",
          "assets/web/memweb/generated/scenarios/work-review-event-v2.webp",
          "方案修改与工作记录",
          "Roadmap and proposal revision record",
        ),
        textTurn("ai", "照片时间与 4 月 16 日评审会议一致。当天文档从 v3 更新到 v5，批注集中在检索范围、验证样例和交付边界。", "The photo timestamp matches the April 16 review meeting. Documents moved from v3 to v5 that day, with comments concentrated on retrieval scope, validation examples, and delivery boundaries."),
        textTurn("user", "不要把三项支持任务算成三个完整项目，它们都只有一两周。", "Do not count the three support tasks as full projects. Each lasted only one or two weeks."),
        textTurn("ai", "已按“一项主项目、三项短期支持”重组时间线。支持任务只统计实际投入和产出，不与主项目里程碑混在一起。", "I reorganized the timeline as one main project plus three short support tasks. Support work is counted only by actual effort and output, separate from the main project's milestones."),
        textTurn("user", "先说我这半年主要在补哪些知识。", "Start with what I spent the past six months learning."),
        textTurn("ai", "三条主线最清晰：检索流程、评测方法、跨团队需求拆解。它们分别对应搜索方案修改、评测清单建立和三次需求澄清会议。", "Three themes stand out: retrieval workflows, evaluation methods, and cross-team requirement breakdown. They map to search-plan revisions, the evaluation checklist, and three requirement-clarification meetings."),
        textTurn("user", "这是上次技术分享的现场，看看它在时间线上处于什么位置。", "This is the last technical sharing session. Place it correctly on the timeline."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/work-tech-sharing-event-v1.webp",
          "assets/web/memweb/generated/scenarios/work-tech-sharing-event-v1.webp",
          "小型会议中的技术分享与检索评测流程",
          "A technical sharing session on retrieval and evaluation workflows",
        ),
        textTurn("ai", "分享发生在第二轮方案通过之后。屏幕内容把检索、存储和评测第一次连成完整流程，因此它不是学习起点，而是阶段性沉淀。", "The session occurred after the second proposal round was approved. The slide connected retrieval, storage, and evaluation into one workflow for the first time, so it marks a synthesis rather than the start of learning."),
        textTurn("user", "把学习过程分阶段，不要只列三个关键词。", "Break the learning into phases instead of listing three keywords."),
        textTurn("ai", "第一阶段补检索基础并做小规模验证；第二阶段建立评测指标和失败样例；第三阶段把需求、检索与评测串成可交付流程，技术分享位于第三阶段。", "Phase one covered retrieval basics and small-scale validation. Phase two established metrics and failure examples. Phase three connected requirements, retrieval, and evaluation into a deliverable workflow, culminating in the technical sharing."),
        textTurn("user", "这些学习最后变成了哪些实际产出？", "What concrete outputs came from that learning?"),
        textTurn("ai", "可追溯的产出有四类：五版主方案、一份评测清单、十二个失败样例及修复说明、一套技术分享材料；另外完成三项支持任务的交付文档。", "Traceable outputs fall into four groups: five main proposal versions, one evaluation checklist, twelve failure cases with fixes, and one technical-sharing package, plus delivery documents for the three support tasks."),
        textTurn("user", "那我反复卡住的地方是什么？", "Where did I repeatedly get stuck?"),
        textTurn("ai", "三个瓶颈重复出现：需求边界确认偏晚、方案验证证据不足、临时支持任务切断主项目的连续时间。", "Three bottlenecks recur: late scope confirmation, insufficient validation evidence, and support tasks fragmenting uninterrupted time on the main project."),
        textTurn("user", "分别有什么证据？不要凭感觉下结论。", "What evidence supports each one? Do not infer them from a feeling."),
        textTurn("ai", "边界问题对应两次范围返工；证据不足对应三次评审补样例；时间碎片化对应主项目两个里程碑各顺延一周，日历中都能定位。", "Scope ambiguity maps to two rounds of rework, weak evidence to three reviews requesting more examples, and fragmented focus to two main-project milestones each slipping by one week, all traceable in Calendar."),
        textTurn("user", "这是我们后来做复盘时画的时间线。", "This is the timeline we drew during the later retrospective."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/work-retrospective-event-v2.webp",
          "assets/web/memweb/generated/scenarios/work-retrospective-event-v2.webp",
          "团队在白板时间线上复盘项目瓶颈",
          "A team reviewing project bottlenecks on a whiteboard timeline",
        ),
        textTurn("ai", "白板上圈出的三个节点正好对应首次范围返工、评测补证和支持任务插入。它与会议纪要及版本提交时间一致，可以作为复盘中的图像证据。", "The three circled points match the first scope rework, the evaluation-evidence request, and an inserted support task. They align with meeting notes and version timestamps and can serve as visual evidence in the review."),
        textTurn("user", "下半年怎么改？要能执行，不要写“加强沟通”。", "What should change in the second half? Make it actionable, not ‘improve communication.’"),
        textTurn("ai", "三项动作：立项 48 小时内签字确认范围；每次评审前按清单准备成功与失败证据；每周预留两个不排会的半天处理主项目。", "Three actions: sign off scope within 48 hours of kickoff, prepare both success and failure evidence from a checklist before each review, and protect two meeting-free half-days per week for the main project."),
        textTurn("user", "年中总结按什么结构写，才能既讲结果也讲成长？", "How should the mid-year summary balance results and growth?"),
        textTurn("ai", "按五部分写：关键任务、学习轨迹、实际产出、反复瓶颈、下半年行动。每部分都链接到日期、文档版本或会议记录，不单独堆感想。", "Use five sections: key work, learning trajectory, actual outputs, recurring bottlenecks, and second-half actions. Each section links to dates, document versions, or meeting records rather than standing on impressions alone."),
        textTurn("user", "数字只用能核对的，别把正常改稿包装成夸张成果。", "Use only verifiable numbers. Do not inflate routine revisions into achievements."),
        textTurn("ai", "已去掉无法核验的效率提升比例，只保留五版方案、十二个失败样例、三项支持交付和两次延期等可追溯数字；年中总结草稿已生成。", "I removed unverifiable efficiency percentages and kept only traceable figures: five proposal versions, twelve failure cases, three support deliveries, and two delays. The mid-year draft is ready."),
        textTurn("user", "这个版本真实，也能看出我接下来具体要改什么，就用它。", "This version feels truthful and shows exactly what I need to change next. Use it."),
      ],
    },
    {
      title: { zh: "家庭预算与订阅复盘", en: "Budget and Subscriptions" },
      avatar: {
        zh: "assets/web/memweb/uid0-person-04.webp",
        en: "assets/web/memweb/uid0-person-04.webp",
      },
      messages: [
        textTurn("user", "最近哪些固定订阅涨价了？下个月哪些服务会自动续费？", "Which recurring subscriptions increased recently, and which services renew automatically next month?"),
        textTurn("ai", "我正在核对近六个月的支付记录、应用商店收据、会员续费通知和日历提醒，并把水电等波动账单单独分类。", "I am comparing six months of payments, app-store receipts, renewal notices, and Calendar reminders, while separating variable utilities from subscriptions."),
        textTurn("user", "先看这笔金额很大的记录，别把一次性消费算成订阅。", "Start with this large payment. Do not classify a one-time purchase as a subscription."),
        imageTurn(
          "user",
          "assets/web/memweb/curated/uid0-money-01.webp",
          "assets/web/memweb/generated/scenarios/budget-payment-en-v2.webp",
          "一次性支付记录",
          "One-time payment record",
        ),
        textTurn("ai", "这笔支付只出现一次，收据类别是家居用品，前后月份没有同商户固定扣款，因此已从订阅和固定支出中排除。", "This payment appears only once, its receipt category is household goods, and there are no recurring charges from the same merchant. It is excluded from subscriptions and fixed expenses."),
        textTurn("user", "能看出具体买了什么吗？我记得是搬家后补的东西。", "Can you tell what I bought? I remember it was after the move."),
        textTurn("ai", "相册同日照片和收据备注都指向一套床品与家居拖鞋，时间也与搬家清单中的“补齐卧室用品”一致。", "The same-day photo and receipt note point to a bedding set and household slippers, matching ‘finish bedroom supplies’ on the moving checklist."),
        textTurn("user", "对，就是这些实物。", "Yes, these are the items."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/budget-household-purchase-event-v1.webp",
          "assets/web/memweb/generated/scenarios/budget-household-purchase-event-v1.webp",
          "一次性购买的床品与家居拖鞋",
          "Bedding and household slippers from a one-time purchase",
        ),
        textTurn("ai", "照片进一步确认这是已经收货的一次性家居消费，不应按月摊成订阅；我会保留在搬家支出类别中。", "The photo further confirms a delivered one-time household purchase. It should not be spread across monthly subscriptions and will remain under moving expenses."),
        textTurn("user", "音乐会员是家庭套餐，家里几个人都在用，不算重复。", "The music membership is a family plan used by several people, so it is not a duplicate."),
        textTurn("ai", "已保留音乐家庭套餐，并将家庭成员共享记录作为保留依据，不把它与个人音乐服务混为重复项。", "I kept the family music plan and linked the family-sharing record as the reason, rather than treating it as a duplicate personal service."),
        textTurn("user", "真正涨价的是哪些？把前后金额说清楚。", "Which services actually increased? Show the old and new amounts."),
        textTurn("ai", "两项：云存储从每月 18 元调到 24 元，视频会员从每月 25 元调到 30 元；最新收据和续费通知都能相互印证。", "Two services increased: cloud storage from 18 to 24 yuan per month and video membership from 25 to 30 yuan. The latest receipts and renewal notices corroborate both changes."),
        textTurn("user", "你说的重复订阅又是哪两个？", "Which two subscriptions are actually duplicated?"),
        textTurn("ai", "是两项个人效率工具：都提供云同步、扫描和文档整理，过去三个月均有使用，但主要功能高度重叠；音乐家庭套餐不在其中。", "They are two personal productivity tools. Both provide cloud sync, scanning, and document organization, and both were used in the last three months, but their main functions overlap heavily. The family music plan is not included."),
        textTurn("user", "下个月每项分别什么时候扣款？", "When will each item charge next month?"),
        textTurn("ai", "5 日云存储、12 日音乐家庭套餐、18 日视频会员、26 日效率工具 A、28 日效率工具 B；每个日期都来自最新续费通知。", "Cloud storage renews on the 5th, family music on the 12th, video on the 18th, productivity tool A on the 26th, and tool B on the 28th. Each date comes from the latest renewal notice."),
        textTurn("user", "我昨晚就是这样对着手机、邮件和日历核账的。", "This is how I compared the phone, emails, and calendar last night."),
        imageTurn(
          "user",
          "assets/web/memweb/generated/scenarios/budget-subscription-review-event-v1.webp",
          "assets/web/memweb/generated/scenarios/budget-subscription-review-event-v1.webp",
          "手机扣款、邮件收据、日历与预算表的核对现场",
          "A review of phone charges, email receipts, Calendar, and a budget sheet",
        ),
        textTurn("ai", "照片时间与昨晚的预算笔记一致。手机扣款顺序、邮件收据和日历圈出的日期能一一对应，五项续费没有遗漏。", "The photo timestamp matches last night's budget note. The phone charges, email receipts, and circled Calendar dates align one by one, with no missing renewals among the five services."),
        textTurn("user", "水电和手机话费为什么没有放进这个续费清单？", "Why are utilities and the phone bill not in this renewal list?"),
        textTurn("ai", "它们是周期账单但金额会随用量变化，不属于固定订阅。我已放入“必要账单”类别，并按近六个月区间单独估算。", "They recur, but their amounts vary with usage, so they are not fixed subscriptions. I placed them under essential bills and estimated them separately using the last six months."),
        textTurn("user", "这五项订阅现在每月合计多少？取消重复项后呢？", "What is the current monthly total for these five subscriptions, and what would it be after removing the duplicate?"),
        textTurn("ai", "当前合计 215 元。若取消 58 元的效率工具 B，同时保留近期使用更多的工具 A，固定订阅将降到每月 157 元。", "The current total is 215 yuan. Canceling the 58-yuan productivity tool B while keeping the more frequently used tool A would reduce fixed subscriptions to 157 yuan per month."),
        textTurn("user", "把真正需要我处理的事项单独列出来。", "List only the items that actually require action."),
        textTurn("ai", "两项：在 18 日前确认是否接受视频会员涨价；在 28 日前取消效率工具 B。云存储涨价已确认继续使用，其余项目无需操作。", "Two actions remain: decide whether to accept the video membership increase before the 18th, and cancel productivity tool B before the 28th. You already chose to keep cloud storage, and the other services need no action."),
        textTurn("user", "把提醒设在扣款前三天，也把调整后的数字写进下月预算。", "Set reminders three days before each charge and put the adjusted amount into next month's budget."),
        textTurn("ai", "已设置 15 日确认视频会员、25 日取消工具 B 两项提醒；下月固定订阅预算更新为 157 元，一次性家居消费和波动账单均未混入。", "Reminders are set for the 15th to review the video membership and the 25th to cancel tool B. Next month's fixed-subscription budget is updated to 157 yuan, excluding the one-time household purchase and variable bills."),
        textTurn("user", "这样就清楚了，哪些是涨价、哪些是重复、哪些只是一次性消费都分开了。", "That is clear. Price increases, duplicates, and one-time purchases are now properly separated."),
      ],
    },
  ];

  const items = Array.from(document.querySelectorAll(".application-item"));
  const visual = document.querySelector("[data-scenario-dialogue]");
  const stream = visual?.querySelector("[data-scenario-stream]");
  const pagination = visual?.querySelector("[data-scenario-pagination]");

  if (!visual || !stream || !pagination) return;

  let activeIndex = 0;
  const currentLanguage = () => (document.documentElement.lang === "zh" ? "zh" : "en");

  const renderPagination = () => {
    const lang = currentLanguage();
    pagination.replaceChildren(
      ...scenarios.map((scenario, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.scenarioIndex = String(index);
        button.setAttribute("aria-label", scenario.title[lang]);
        button.setAttribute("aria-pressed", String(index === activeIndex));
        button.addEventListener("click", () => activate(index));
        return button;
      }),
    );
  };

  const render = ({ animate = true } = {}) => {
    const lang = currentLanguage();
    const scenario = scenarios[activeIndex];
    const userAvatar =
      scenario.avatar?.[lang] ??
      (lang === "zh"
        ? "assets/web/memweb/uid0-person-01.webp"
        : "assets/web/memweb/uid10-person-01.webp");
    const messages = scenario.messages.map((turn, index) => {
      const article = document.createElement("article");
      const avatar = document.createElement("span");
      const avatarImage = document.createElement("img");

      article.className = turn.role === "user" ? "is-user" : "is-ai";
      article.dataset.turn = String(index + 1).padStart(2, "0");
      avatar.className = "application-ai-message-avatar";
      avatarImage.src = turn.role === "user" ? userAvatar : "assets/web/xiaobu-avatar.webp";
      avatarImage.alt = "";
      avatarImage.className = turn.role === "user" ? "is-user" : "is-xiaobu";
      avatarImage.loading = "lazy";
      avatarImage.decoding = "async";
      avatar.append(avatarImage);
      article.append(avatar);

      if (turn.src) {
        const imageBubble = document.createElement("div");
        const image = document.createElement("img");
        imageBubble.className = "application-ai-image-bubble";
        image.src = turn.src[lang];
        image.alt = turn.alt[lang];
        image.loading = "eager";
        image.decoding = "async";
        imageBubble.append(image);
        article.append(imageBubble);
      } else {
        const bubble = document.createElement("p");
        bubble.textContent = turn.text[lang];
        article.append(bubble);
      }

      return article;
    });
    stream.replaceChildren(...messages);
    stream.scrollTop = 0;
    renderPagination();

    if (animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      visual.animate(
        [
          { opacity: 0.72, transform: "translateY(8px)" },
          { opacity: 1, transform: "translateY(0)" },
        ],
        { duration: 260, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
      );
    }
  };

  function activate(index, { focus = false } = {}) {
    if (!scenarios[index] || !items[index]) return;
    activeIndex = index;
    items.forEach((item, itemIndex) => {
      item.open = itemIndex === index;
    });
    render();
    if (focus) items[index].querySelector("summary")?.focus({ preventScroll: true });
  }

  items.forEach((item, index) => {
    const summary = item.querySelector("summary");
    summary?.addEventListener("click", (event) => {
      event.preventDefault();
      if (activeIndex === index) return;
      activate(index);
      item.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    });
  });

  window.addEventListener("mobilemem:languagechange", () => render({ animate: false }));
  render({ animate: false });
})();
