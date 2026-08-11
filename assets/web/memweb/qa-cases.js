globalThis.MobileMemQACases = {
  typeOrder: [
    "single_hop",
    "multi_hop",
    "knowledge_update",
    "temporal_reasoning",
    "implicit_preference",
    "abstention",
    "visual_reasoning",
  ],
  typeCopy: {
    single_hop: {
      zh: "单跳推理",
      en: "Single-hop",
    },
    multi_hop: {
      zh: "多跳推理",
      en: "Multi-hop",
    },
    knowledge_update: {
      zh: "知识更新",
      en: "Knowledge update",
    },
    temporal_reasoning: {
      zh: "时序推理",
      en: "Temporal reasoning",
    },
    implicit_preference: {
      zh: "隐式偏好",
      en: "Implicit preference",
    },
    abstention: {
      zh: "拒答",
      en: "Abstention",
    },
    visual_reasoning: {
      zh: "视觉推理",
      en: "Visual reasoning",
    },
  },
  users: {
    uid0: {
      language: "zh",
      cases: {
        single_hop: [
          {
            id: "0_q_8",
            question:
              "春节返乡前把阿拉斯加送去寄养时，我挑店最看重的是什么？\nA. 离家最近最方便\nB. 价格最低最划算\nC. 店面最大最热闹\nD. 环境和护理质量\nE. 送养速度最快\nF. 活动优惠最多",
            answer: "D. 环境和护理质量",
            format: "multiple_choice",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid0-evidence-pet.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_8",
                text: "我更看重环境和护理。",
              },
              {
                sessionId: "0_8",
                text: "虽然价格略贵一点，但我放心。",
              },
            ],
          },
          {
            id: "0_q_15",
            question:
              "1月31日下午我和舅妈一起算完账后，最后做了什么决定？\nA. 调整两款商品的进货数量并提交订单\nB. 取消所有订单先再等等\nC. 只保留洗发水先下单\nD. 先加大进货量再观察\nE. 改成线下拿货再说\nF. 先让店员代为下单",
            answer: "A. 调整两款商品的进货数量并提交订单",
            format: "multiple_choice",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid0-evidence-shop.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_10_4",
                text: "1月31日下午，王景川和舅妈一起在店里核算进货成本和利润后，帮她调整了两款商品的进货数量，并最终按下提交订单，完成了这次网上进货决策。",
              },
              {
                sessionId: "0_10_4",
                text: "最后就是调了数量，没敢一下子进太多。先稳一点，免得压在手里。",
              },
            ],
          },
        ],
        multi_hop: [
          {
            id: "0_q_251",
            question:
              "我把婚礼资金底线和双方案预算定下来之后，5月4日那晚又把哪些东西摆出来逐项核算了？",
            answer: "酒店和婚庆公司的报价单。",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_27_3",
                text: "2025年4月6日晚，王景川和未婚妻蔡雪宁第一次把餐桌清空，摊开笔记本、电脑和温水，一起正式讨论婚礼资金底线，并开始把存款、理财和工资流水逐项列清。",
              },
              {
                sessionId: "0_27_3",
                text: "2025年5月4日晚上，王景川和蔡雪宁把几家酒店与婚庆公司的报价单摊在一起逐项核算，现场一边看一边用计算器把各项费用相加。",
              },
            ],
          },
          {
            id: "0_q_253",
            question: "我在5月10日那次出差高铁上，本来想做什么学习安排，后来为什么没继续下去？",
            answer: "我本来想继续看工商管理网课，但因为犯困和车厢干扰，只看了十几分钟就中断了。",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid0-evidence-train.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_25_3",
                text: "2025-05-10傍晚，王景川在出差高铁上原本打算打开平板继续看工商管理网课，但刚坐下就明显犯困，学习计划没能顺利展开。",
              },
              {
                sessionId: "0_25_3",
                text: "高铁车厢里持续有人走动，加上孩子哭声和行李箱拖动声，王景川即使戴着耳机也很难集中注意力，课程只看了十几分钟就被迫中断。",
              },
            ],
          },
        ],
        knowledge_update: [
          {
            id: "0_q_515",
            question: "我现在对婚礼流程最想守住的原则是什么？",
            answer: "先照顾感受，再谈方案和执行",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_41_5",
                text: "婚礼筹备后期，王景川和蔡雪宁形成了一个共识：先照顾彼此感受，再谈方案和执行；两人还约定在婚礼之外多做些能放松情绪的小事，减少对预算和风险的反复争论。",
              },
              {
                sessionId: "0_41_5",
                text: "我以前觉得把事情排顺了就行，但这次让我记住了，婚礼不是工作安排。她那天想要的是被好好照顾到，不是按表格被推进去。",
              },
            ],
          },
          {
            id: "0_q_552",
            question: "我那天把“管住花钱”改成了什么说法，才把气氛缓下来？",
            answer: "一起有计划地花",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_78_1",
                text: "“我就把‘管住花钱’改成了‘一起有计划地花’。”",
              },
              {
                sessionId: "0_78_2",
                text: "“王景川随即调整说法，把‘管住花钱’改成‘一起有计划地花’，避免让气氛继续僵住。”",
              },
            ],
          },
        ],
        temporal_reasoning: [
          {
            id: "0_q_745",
            question: "那晚我先订宠物寄养，再开始正式看地图，前后大概隔了多久？",
            answer: "大约半小时左右",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_71_3",
                text: "2025年9月28日19:40，王景川在外卖未到时拨打了合肥市瑞宠动物医院的电话咨询宠物寄养，最终决定先把位置订下来。",
              },
              {
                sessionId: "0_71_4",
                text: "2025年9月28日20点10分左右，王景川和蔡雪宁把清淡外卖摆在茶几上，打开电脑地图，边吃边讨论国庆自驾路线。",
              },
            ],
          },
          {
            id: "0_q_741",
            question:
              "我和雪宁第一次把婚礼资金底线摊开来谈，到后来做最后一次总账，前后大概隔了多久？",
            answer: "大约五个半月",
            format: "open_ended",
            difficulty: "hard",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_27_8",
                text: "2025年4月6日晚，王景川和未婚妻蔡雪宁第一次把餐桌清空，摊开笔记本、电脑和温水，一起正式讨论婚礼资金底线。",
              },
              {
                sessionId: "0_27_8",
                text: "2025年9月28日晚上，王景川和蔡雪宁把窗户半掩着，在有些凉意的夜里做了婚礼前最后一次总账核对。",
              },
            ],
          },
        ],
        implicit_preference: [
          {
            id: "0_q_1034",
            question: "我遇到春节后重新调作息这件事，在运动方式上你的建议是什么？",
            answer: "循序渐进，慢跑快走交替更适合我",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_13_6",
                text: "我也慢慢发现自己不太适合那种特别猛的训练。慢跑、快走交替，或者下班后去公园走一走，反而更能坚持。",
              },
              {
                sessionId: "0_13_6",
                text: "这段时间里，王景川更清楚地意识到自己适合循序渐进的运动方式，尤其是下班后去公园慢跑或快走交替，而不是追求高强度训练。",
              },
            ],
          },
          {
            id: "0_q_1036",
            question:
              "我遇到刚开始列学习清单又被工作和备婚打断这件事，在推进方式上你的建议是什么？",
            answer: "把目标拆小，先从一件能做的事开始",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_25_1",
                text: "后来我也慢慢不追求那种每天两小时的高强度了，反而更愿意把目标拆小一点，降低每天的门槛。",
              },
              {
                sessionId: "0_25_1",
                text: "她让我别一下子想太大，先分小一点，我听完就没那么慌了。",
              },
            ],
          },
        ],
        abstention: [
          {
            id: "0_q_1227",
            question: "我做春季体检缴费时，单位报销和自费大概是怎么分开的？",
            answer: "根据现有对话和记忆，无法回答这个问题。",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: null,
                text: "现有记忆记录了体检与缴费，但没有单位报销和个人自费的拆分金额。",
              },
            ],
          },
          {
            id: "0_q_1307",
            question: "8月下旬我和雪宁挑新郎服饰时，后来有没有最终确定西装和领带的具体颜色组合？",
            answer: "根据现有对话和记忆，无法回答这个问题。",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: null,
                text: "现有记忆只记录了正式、耐看、不过分夸张的选衣标准，没有最终西装和领带颜色。",
              },
            ],
          },
        ],
        visual_reasoning: [
          {
            id: "0_q_813",
            question: "那次傍晚去公园跑步的画面里，我在什么地方坐着休息？",
            answer: "长椅",
            format: "open_ended",
            difficulty: "hard",
            image: "assets/web/memweb/qa/uid0-visual-01.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_13_3",
                text: "傍晚的合肥融创体育公园，天色微暗、操场与跑道被暖黄色灯光照亮，广场上人们跳着整齐的广场舞，周围有人悠闲散步，跑道上一位下班后着便装的人在慢跑与快走间转换，表情专注放松，跑完后坐在场边长椅上喘气休息，旁边绿化整齐，远处保安正沿着步道巡逻，整体气氛安静而有活力。",
              },
            ],
          },
          {
            id: "0_q_821",
            question: "春节后那次我和母亲一起做晚饭的场景里，桌上摆的是哪几样家常菜？",
            answer: "番茄鸡蛋、清炒西兰花和凉拌黄瓜。",
            format: "open_ended",
            difficulty: "hard",
            image: "assets/web/memweb/qa/uid0-visual-02.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "0_13_6",
                text: "傍晚温暖的室内灯光下，整洁的家用厨房与小餐厅连在一起，桌上摆着番茄炒蛋、清炒西兰花和凉拌黄瓜等清淡家常菜，一位中年母亲在灶台前收拾餐具，旁边的成年人坐在餐桌边夹菜、微笑交谈，氛围安静温馨。",
              },
            ],
          },
        ],
      },
    },
    uid10: {
      language: "en",
      cases: {
        single_hop: [
          {
            id: "10_q_60",
            question:
              "What did I order for the late-night office dinner during the board-prep crunch?\nA. Pizza delivery to the office\nB. Sushi delivery to the office\nC. A burger and fries run\nD. Tacos from a nearby taqueria\nE. A grain bowl from home\nF. Ramen takeout for the team",
            answer: "B. Sushi delivery to the office",
            format: "multiple_choice",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-sushi.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_34",
                text: "Michael ordered sushi delivery to the office instead of greasy fast food because he wanted something lighter while staying late.",
              },
              {
                sessionId: "10_34",
                text: "It was sushi tonight, not pizza. I only said the takeout habit part because it’s starting to feel automatic.",
              },
            ],
          },
          {
            id: "10_q_43",
            question:
              "What did I decide about the March Bay Area hike ride, and why?\nA. I booked a regional train ticket so the trip would stay simple and avoid driving.\nB. I planned to drive so I could leave whenever I wanted.\nC. I asked Jason to handle all the transportation details.\nD. I decided to take a rideshare because it seemed faster.\nE. I stayed undecided and never actually booked anything.\nF. I bought a bus ticket because it was the cheapest option.",
            answer:
              "A. I booked a regional train ticket so the trip would stay simple and avoid driving.",
            format: "multiple_choice",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-hike-ticket.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_25",
                text: "On 2025-03-15 around 10:30 AM, Michael sat at his laptop comparing transportation options for the Bay Area hiking day Jason Miller had suggested.",
              },
              {
                sessionId: "10_25",
                text: "He decided to book a regional train ticket so he could avoid driving out to the trailhead and make the trip easier after the hike.",
              },
            ],
          },
        ],
        multi_hop: [
          {
            id: "10_q_298",
            question:
              "How many people were in the Denver train plan I booked for my parents’ anniversary trip?",
            answer: "Three people: me, Daniel, and Laura.",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-family-train.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_56",
                text: "Michael sat down in the evening to book a train ticket from San Francisco to Denver so he could attend Daniel and Laura Carter’s anniversary in person.",
              },
              {
                sessionId: "10_56",
                text: 'This person portrait corresponds to Michael Carter, Daniel Carter, and Laura Carter, showing the main people involved in "Booking train to Denver for parents’ anniversary and family time".',
              },
            ],
          },
          {
            id: "10_q_278",
            question:
              "On the waterfront run, who was with me, and what did he notice about my breathing?",
            answer: "Tyler Green; he said my breathing sounded smoother than it had in February",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_9_7",
                text: "On 2025-05-10 around 8:00 a.m., Michael met Tyler Green near the Ferry Building on the Embarcadero and started a waterfront run together in the foggy morning air.",
              },
              {
                sessionId: "10_9_7",
                text: "By the end of the run, Tyler noticed Michael's breathing sounded smoother than it had been in February.",
              },
            ],
          },
        ],
        knowledge_update: [
          {
            id: "10_q_496",
            question: "On the beach at sunset, what did I realize after Jason buried my phone?",
            answer: "That I could be temporarily unavailable without anything falling apart.",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-beach.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_48_6",
                text: "Yeah, totally. I finally looked up and actually saw the sky going from orange to purple. My brain felt quieter than it had all weekend.",
              },
              {
                sessionId: "10_48_6",
                text: "The main takeaway is that you realized you could be temporarily unavailable and the startup would survive.",
              },
            ],
          },
          {
            id: "10_q_481",
            question:
              "What was my current thinking about the side project after the refactor night?",
            answer: "The simplified version felt like a better foundation.",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_8_5",
                text: "Michael committed the simplified changes that night, feeling a jolt of tension because cutting features felt like admitting he could not do everything he had planned.",
              },
              {
                sessionId: "10_8_5",
                text: "The simplified version felt like a better foundation.",
              },
            ],
          },
        ],
        temporal_reasoning: [
          {
            id: "10_q_693",
            question:
              "How long after the dental reminder did I finally pay the bill online?\nA. The same evening, shortly after opening it.\nB. The next morning.\nC. A few days later.\nD. About a week later.\nE. After the next paycheck arrived.\nF. I paid it before opening the reminder.",
            answer: "A. The same evening, shortly after opening it.",
            format: "multiple_choice",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-dental.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_53",
                text: "Opened an overdue reminder from BayBridge Family Dentistry about a filling from earlier in the year and realized the balance was higher than expected because insurance covered less than Michael had assumed.",
              },
              {
                sessionId: "10_53",
                text: "Paid the dental bill online that evening after reading the mailed notice, treating it as an immediate overdue expense that needed to be cleared.",
              },
            ],
          },
          {
            id: "10_q_660",
            question:
              "How long after I first noticed the apartment was cramped did I end up rearranging the room instead of moving?",
            answer: "About three months.",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-apartment.jpg",
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_3_9",
                text: "On 2025-01-12 in the early evening, Michael noticed his apartment had become cramped enough that moving around his desk, couch, guitar stand, pull-up bar, and stacked boxes required careful navigation.",
              },
              {
                sessionId: "10_3_9",
                text: "On 2025-04-15 around 20:30, Michael dragged the couch closer to the window and turned his desk to face the wall instead of the kitchen, creating a new layout for the room.",
              },
            ],
          },
        ],
        implicit_preference: [
          {
            id: "10_q_1022",
            question: "For my keyboard upgrade, what matters most to me?",
            answer:
              "Comfort, solid build quality, and a quieter typing feel without flashy extras.",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-evidence-keyboard.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_21",
                text: "Switch feel and typing comfort, mostly. I don't care about flashy stuff. I just want something solid and not too noisy.",
              },
              {
                sessionId: "10_21",
                text: "It would matter every workday. My hands get tired in long refactors, so that's not just a one-off mood thing.",
              },
            ],
          },
          {
            id: "10_q_1011",
            question:
              "Would I probably choose the formal ML course or the lighter self-directed path now?",
            answer: "The lighter self-directed path with small startup projects.",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: "10_2_6",
                text: "By the March 12 lunchtime check-in, I told her I wasn’t enrolling in the formal course. I wanted a self-directed learning plan tied to small startup projects instead.",
              },
              {
                sessionId: "10_2_6",
                text: "It felt more honest. I could break it into smaller, structured practice blocks and connect it to real work problems instead of buying into the glossy bootcamp-style promise.",
              },
            ],
          },
        ],
        abstention: [
          {
            id: "10_q_1214",
            question: "What kind of ramen did I order during the refactor night with Alex?",
            answer: "This information is not available in the memory.",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: null,
                text: "The memory records ordering ramen during the refactor night, but not the ramen type.",
              },
            ],
          },
          {
            id: "10_q_1259",
            question: "What model was my old desk chair before I bought the new one?",
            answer: "This information is not available in the memory.",
            format: "open_ended",
            difficulty: "medium",
            image: null,
            imageLayout: null,
            evidence: [
              {
                sessionId: null,
                text: "The memory mentions replacing the old chair, but never records its model.",
              },
            ],
          },
        ],
        visual_reasoning: [
          {
            id: "10_q_834",
            question:
              "Late that evening, with apartment noise still bothering me, which headphones did I end up comparing online?",
            answer: "Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-visual-01.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_10",
                text: "Item: Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones · Store: Amazon.com Services LLC · Price: $398.0",
              },
            ],
          },
          {
            id: "10_q_862",
            question:
              "Around that holiday planning screen, with the notebook still open beside me, which destination was printed on the ticket?",
            answer: "Sausalito",
            format: "open_ended",
            difficulty: "medium",
            image: "assets/web/memweb/qa/uid10-visual-02.png",
            imageLayout: "screenshot",
            evidence: [
              {
                sessionId: "10_4",
                text: "San Francisco → Sausalito · F121 · Economy Car 02 Seat 08B",
              },
            ],
          },
        ],
      },
    },
  },
};
