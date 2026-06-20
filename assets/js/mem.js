/* MobileMem · On-Device Memory */

(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const I18N = {
    en: {
      'nav.abstract': 'Overview',
      'nav.synthesis': 'Memory Synthesis',
      'nav.dataset': 'MobileMem Dataset',
      'nav.omni': 'MobileMem-Omni Dataset',
      'ov.kicker': 'Overview', 'ov.title': 'Overview of On-Device Memory',
      'ov.toc1': '§1 · Introduction', 'ov.toc2': '§2 · Overview of On-Device Memory', 'ov.toc3': '§2.1 · Problem Formulation',
      'ov.note': 'Reserved for finalized paper text.',
      'syn.kicker': '§3 · Synthesis', 'syn.title': 'Knowledge Graph-Grounded On-Device Memory Synthesis',
      'syn.note': 'Reserved for finalized paper text.',
      'ch4.title': 'MobileMem Dataset', 'ch4.lead': 'MobileMem is designed to evaluate memory systems in real-world mobile environments.',
      'ch4.t1': 'Design Principle', 'ch4.t2': 'KEME Framework', 'ch4.t3': 'QA Synthesis & Quality Control', 'ch4.t4': 'Experiments & Analysis',
      'ch5.title': 'MobileMem-Omni Dataset', 'ch5.lead': 'MobileMem, featuring real-user participation, multimodal interactions, and multi-source content, is established through a multi-stage pipeline.',
      'sub.scene': 'Scenarios', 'sub.build': 'Construction', 'sub.persona': 'Persona', 'sub.events': 'Events', 'sub.synth': 'Synthesis', 'sub.results': 'Main results', 'sub.analysis': 'Analysis', 'sub.agents': 'Agents',
      'lang.toggle': '中文',
      'hero.badge': 'Preprint · OPPO × OpenKG',
      'hero.t1': 'MobileMem',
      'hero.t2': 'On-Device Memory for Continually Evolving Agents',
      'hero.sub': 'MobileMem, featuring real-user participation, multimodal interactions, and multi-source content, is established through a multi-stage pipeline.',
      'hero.affil': 'OPPO · OpenKG',
      'cta.paper': 'Paper', 'cta.code': '</>Code', 'cta.data': '◈Dataset', 'cta.results': 'Email',
      'orbit.core': 'MEMORY\nCORE',
      'field.hint': 'DRAG TO ROTATE · CLICK A NODE',
      'abs.kicker': 'Overview',
      'abs.text': 'As mobile assistants evolve into <strong>long-term companions</strong>, memory becomes a foundational capability. Yet real mobile memory is not a clean chat log —it is a continuous, <strong>heterogeneous and multi-source</strong> stream of human-assistant dialogues interleaved with passive observations of third-party apps. We present <strong>MobileMem</strong>, an on-device memory benchmark, together with <strong>KEME</strong>, a knowledge-guided experience synthesis framework that turns fragmented app traces into coherent, continually evolving lifelong trajectories. A multimodal extension, <strong>MobileMem-Omni</strong>, further stresses cross-modal and multilingual memory.',
      'stat.ondevice': 'On-device', 'stat.ondevice.l': 'Memory setting',
      'stat.users': 'User trajectories', 'stat.qa': 'Open QA', 'stat.images': 'Images', 'stat.types': 'Question types',
      'stat.gap': '<50%', 'stat.gap.l': 'Best memory system',
      'fig.scene.t': 'Personal memory agent', 'fig.scene.d': 'MobileMem performs cross-time facial recognition to locate a years-old birthday scene from a vast photo archive.',
      'fig.traj.t': 'Synthesized trajectory', 'fig.traj.d': 'A long-horizon, multi-session trajectory produced by KEME.',
      'fig.hdl.t': 'Trajectory length', 'fig.hdl.d': 'Length distribution of KEME hard-distractor trajectories.',
      'fig.hdr.t': 'Evidence rank', 'fig.hdr.d': 'KEME pushes answer-supporting evidence toward less favorable retrieval ranks.',
      'fig.radar.t': 'Event-type radar', 'fig.radar.d': 'LLM-Judge (%) by interaction language and event span.',
      'fig.case.t': 'Case analysis', 'fig.case.d': 'Errors arise from retrieving same-type but irrelevant images or events.',
      'fig.pda.t': 'Perception-Decision-Action', 'fig.pda.d': 'The position of MobileMem within the on-device agent loop.',
      'prin.kicker': 'Design Principles', 'prin.title': 'What on-device memory really demands',
      'prin.lead': 'MobileMem is designed to evaluate memory systems in real-world mobile environments.',
      'prin.p1.t': 'Heterogeneity & multi-source', 'prin.p1.d': 'Beyond human-assistant chat, memory must absorb real-time message streams from a complex ecosystem of third-party apps —heterogeneous in both format and semantics.',
      'prin.p2.t': 'Observation + participation', 'prin.p2.d': 'A non-intrusive assistant learns mostly by passively observing user-app activity, interleaved with occasional explicit dialogues —like an ambient assistant running in the background.',
      'prin.p3.t': 'Realism-guided synthesis', 'prin.p3.d': 'Raw multi-app logs carry sensitive personal data. MobileMem adopts a realism-guided construction paradigm that preserves authenticity while fully protecting user privacy.',
      'keme.kicker': 'Core Framework', 'keme.title': 'KEME: knowledge-guided experience synthesis for evolving memory',
      'keme.lead': 'KEME treats fragmented user-app sessions as foundational knowledge anchors, then hierarchically synthesizes them into a coherent, continually evolving long-horizon trajectory.',
      'keme.a1.h': 'Planner', 'keme.a1.i1': 'Knowledge-guided planner', 'keme.a1.i2': 'Builds temporal event graph', 'keme.a1.i3': 'Recursive expansion',
      'keme.a2.h': 'Grounder', 'keme.a2.i1': 'Knowledge anchor grounder', 'keme.a2.i2': 'Binds app sessions to events', 'keme.a2.i3': 'Non-contradiction context',
      'keme.a3.h': 'Realizer + Reviser', 'keme.a3.i1': 'Experience realizer', 'keme.a3.i2': 'Experience-driven reviser', 'keme.a3.i3': 'Persona evolution',
      'keme.loop': 'A closed loop of <b>top-down knowledge guidance</b> and <b>bottom-up experience evolution</b> —an expansion-refinement alternation that keeps long-horizon coherence while disclosing and updating the persona over time.',
      'fig.keme.t': 'KEME framework', 'fig.keme.d': 'An illustrative example of closed-loop trajectory synthesis with anchored knowledge and experience.',
      'ds.kicker': 'MobileMem Dataset', 'ds.title': 'From anchored knowledge to evaluable QA',
      'ds.lead': 'A bottom-up pipeline turns synthesized trajectories into cross-session question-answer pairs, with multi-staged quality control.',
      'ds.s1.t': 'Knowledge anchors', 'ds.s1.d': 'Fragmented user-app sessions are treated as immutable foundational anchors.',
      'ds.s2.t': 'Trajectory synthesis', 'ds.s2.d': 'KEME expands a persona into a long-horizon, evolving multi-session trajectory.',
      'ds.s3.t': 'QA synthesis', 'ds.s3.d': 'A bottom-up traversal builds single- and cross-session QA from leaves to root.',
      'ds.s4.t': 'Quality control', 'ds.s4.d': 'Rule-based validation, LLM assessment and manual review ensure reliability.',
      'ds.todo': 'More dataset statistics and schema details —to be added once the paper is finalized.',
      'res.kicker': '§4.4 · Experiments', 'res.title': 'Specialized memory frameworks lead —yet all stay low',
      'res.lead': 'On MobileMem, specialized memory-augmented frameworks consistently outperform Long Context and RAG baselines —yet the best system reaches only 39.4% LLM-Judge with GPT-5.4-mini, underscoring how challenging on-device memory remains.',
      'res.m1.n': '39.4%', 'res.m1.l': 'Best LLM-Judge (EverMemOS)', 'res.m2.n': '10', 'res.m2.l': 'Memory methods', 'res.m3.n': '2', 'res.m3.l': 'LLM backbones', 'res.m4.n': '7', 'res.m4.l': 'Task types',
      'res.methods': 'Methods: Long Context, NaiveRAG, LangMem, Mem0, LightMem, EverMemOS (+ multimodal: SigLIP+NaiveRAG, UniversalRAG, M²A) · Backbones: GPT-5.4-mini, Qwen3-VL-8B-Instruct · Embedding: all-MiniLM-L6-v2 · retrieval K = 15.',
      'res.hard.t': 'Hard-distractor synthesis', 'res.hard.d': 'KEME can synthesize answer-preserving but retrieval-harder trajectories, pushing answer-supporting evidence toward less favorable retrieval ranks —so how evidence and distractors are arranged can matter as much as trajectory length.',
      'res.todo': 'Per-task scores for every method are in the §5 results table below.',
      'omni.chapter': 'MobileMem-Omni Dataset',
      'omni.s0.scene.title': 'Personal Memory Agent',
      'omni.s0.scene.q': 'MobileMem acts as the user\'s personal memory agent, automatically understanding user intent, performing cross-time facial recognition to associate the daughter\'s identity across years, locating the 2016 birthday scene from a vast photo archive, and returning the photo of the family of three gathered around the birthday cake.',
      'omni.s0.layer.title': 'Unified Memory Layer',
      'omni.s0.layer.q': 'MobileMem breaks down data silos between apps, unifying data from chat, social media, photos, reading, shopping, and calendar into a single "memory layer," enabling the phone to "remember" your relationships, interests, and context like a human, and proactively deliver intelligent services across scenarios.',
      'omni.s0.pda.title': 'Perception-Decision-Action',
      'omni.s0.pda.q': 'The Position of MobileMem within the Perception-Decision-Action Loop Architecture.',
      'omni.s1.title': 'Benchmark Construction',
      'omni.s1.a1.t': '16 Trajectories · Multi-Stage Pipeline',
      'omni.s1.a2.t': 'Multimodal Message Stream',
      'omni.s1.a3.t': 'Multi-Source Visual & Multilingual Memory',
      'omni.s1.q1': 'As illustrated in Figure, MobileMem, featuring real-user participation, multimodal interactions, and multi-source content, is established through a multi-stage pipeline. Specifically, the benchmark includes 16 distinct user trajectories.',
      'omni.s1.q2': 'The user trajectory is modeled as a stream of multimodal messages with authenticity grounded partially in real-world data, complemented by synthetic generation, encompassing both textual dialogues and visual content simulating real user mobile device usage.',
      'omni.s1.q3': 'A key feature is that these visual content originate from diverse sources, including device cameras, mobile applications, and shared media. This multi-source design ensures that the benchmark reflects the heterogeneous nature of real-world mobile experiences. Additionally, the benchmark supports multilingual interactions, where users may communicate in different languages based on their linguistic background, and memory systems must maintain cross-lingual consistency.',
      'omni.s1.fig': 'The overview of MobileMem framework.',
      'omni.s2.title': 'Mobile Persona and Memory Modeling',
      'omni.s2.a1.t': 'Hybrid Persona Construction',
      'omni.s2.a2.t': 'Personal Knowledge Graph Generation',
      'omni.s2.q1': 'To balance authenticity, diversity, and scalability, MobileMem constructs personas through a hybrid approach: half are derived from representative hired participants, that references real participant data to produce persona types that are relatively authentic yet distinct from the original reference individuals. Based on these personas, we further design a schema that serves as the core memory structure of MobileMem, systematically organizing each user\'s persona information, historical status, and temporal milestones into a unified representation for realistic mobile interaction and memory simulation.',
      'omni.s2.q2': 'Each persona is represented by three components: a basic information vector capturing core identity and background, an initial state vector capturing the user\'s status and daily patterns before interaction begins, and a personal knowledge graph constructed from their social relationships.',
      'omni.s2.fig': 'Profile schema for mobile persona and memory modeling.',
      'omni.s3.title': 'Knowledge-Graph-Driven Event Building',
      'omni.s3.q1': 'Based on the persona\'s knowledge graph, we generate a stream of events that form the backbone of each persona\'s trajectory. The event generation process is divided into three stages: Important Date Collection, Event Building, and Step Breakdown.',
      'omni.s3.q2': 'Using these diverse and personalized important dates as anchors, we build an event sequence for each persona that aligns with their basic information vector and initial state vector. We use GPT-5.1 to generate a personalized event sequence spanning one year.',
      'omni.s3.q3': 'Each event is decomposed into a sequence of short-term sub-event steps, where the sub-event step sequence is temporally ordered and covers the complete development of the event from start to end.',
      'omni.s3.fig': 'Multi-source content distribution across mobile data sources.',
      'omni.s4.title': 'Data Synthesis Pipeline',
      'omni.s4.a1.t': 'Multimodal Dialogue Synthesis',
      'omni.s4.a2.t': 'Memory Question Generation',
      'omni.s4.a3.t': 'Quality Control',
      'omni.s4.q1': 'We transform the event steps into concrete multimodal dialogues that simulate real user-AI interactions. The process is divided into two phases: Memory Point Decomposition, where each event step is decomposed into fine-grained textual and visual memory points, and Session Generation, where these memory points are synthesized into natural dialogue turns and corresponding images.',
      'omni.s4.q2': 'To systematically assess memory system performance, we construct evaluation questions based on the generated memory points and step information using GPT-5.1. The question set covers seven predefined categories: (1) Single-Hop: retrieve a single factual piece; (2) Multi-Hop: synthesize information from multiple factual pieces; (3) Knowledge Update: incorporate new information and revise outdated memory; (4) Temporal Reasoning: capture time-related cues and reason; (5) Implicit Preference: infer latent user attributes or preferences; (6) Abstention: correctly decline to answer when information is absent; (7) Visual Reasoning: interpret and reason over visual content.',
      'omni.s4.q3': 'After the filtering process, a total of 19,060 images and 7,415 question-answer pairs are retained in the final benchmark.',
      'omni.s4.fig': 'Question-answer pairs synthesized from multimodal trajectories.',
      'omni.s5.title': 'Main Results and Analysis',
      'omni.s5.q1': 'As shown in Table, we observe a clear performance hierarchy across different families of approaches. Specialized memory-augmented frameworks consistently outperform long context and RAG types of methods across almost all tasks and backbone models.',
      'omni.s5.q2': 'As shown in Figure, incorporating image captions into NaiveRAG yields a trade-off: performance improves on visual-reasoning questions but declines on text-oriented questions.',
      'omni.s5.q3': 'As shown in Figure, we present common errors observed across different methods. For multimodal memory approaches, they tend to generate erroneous memories by retrieving images of the same type as the target but irrelevant to the actual answer, such as confusing similar screenshots from different contexts.',
      'omni.s5.fig1': 'LLM-Judge performance (%) changes of NaiveRAG: captions improve visual reasoning but degrade other text-oriented questions.',
      'omni.s5.fig2': 'Radar chart of event type LLM-Judge performance (%). Events are divided by interaction language: Chinese, English; and by event span: short-term, medium-term, long-term.',
      'omni.s5.fig3': 'Case analysis. (a) shows the dialogue containing the correct answer, while (b), (c), and (d) show the dialogue sources of incorrect memory information from memory methods.',
      'tbl.method': 'Method', 'tbl.gpt': 'GPT-5.4-mini', 'tbl.qwen': 'Qwen3-VL-8B-Instruct',
      'tbl.textual': 'Textual Memory Methods', 'tbl.multimodal': 'Multimodal Memory Methods',
      'omni.tbl.cap': 'Question-answering performance of methods. Scores for each task are evaluated using LLM-as-a-Judge.',
      'ag.kicker': 'Mobile Agents', 'ag.title': 'From a benchmark to on-device intelligence',
      'ag.lead': 'MobileMem is designed to plug into real mobile-agent pipelines and inform how on-device intelligence is defined and measured.',
      'ag.c1.t': 'Ecosystem', 'ag.c1.d': 'A unified benchmarking framework that fits task understanding, memory retrieval QA, search, safety and execution modules in real product pipelines.',
      'ag.c2.t': 'Standardization', 'ag.c2.d': 'Unifying foundational, cognitive, preference and visual memory, grounded in real user data and year-long temporal spans.',
      'ag.c3.t': 'On-device intelligence', 'ag.c3.d': 'Clear metrics for memory quality, retrieval accuracy and reasoning robustness —essential for tuning and deploying on-device models.',
      'ag.c4.t': 'User memory value', 'ag.c4.d': "Centering the user's long-term multimodal memory as the unit of personalization, enabling genuinely context-aware, evolving assistance.",
      'ag.oppo': "MobileMem has been integrated into OPPO's AI assistant development pipeline to evaluate and enhance long-term memory in production-grade mobile scenarios.",
      'bib.kicker': 'Citation', 'bib.title': 'BibTeX', 'bib.copy': 'Copy', 'bib.todo': 'Author list and venue —to be finalized.',
      'fig.cite.t': 'One memory layer', 'fig.cite.d': 'MobileMem unifies chat, social, photos, reading and shopping into a single memory layer across apps.',
      'team.kicker': 'Affiliation', 'team.title': 'Institutions',
      'team.eyebrow': 'This work is jointly conducted by the following institutions',
      'team.views': 'Page views',
      'team.note': 'MobileMem is jointly developed by OPPO and OpenKG.',
      'footer.tag': 'On-Device Memory',
    },
    zh: {
      'nav.abstract': '概览',
      'nav.synthesis': '记忆合成',
      'nav.dataset': 'MobileMem 数据集',
      'nav.omni': 'MobileMem-Omni Dataset',
      'lang.toggle': 'EN',
      'hero.t1': 'MobileMem',
      'hero.t2': '面向持续进化智能体的端侧记忆',
      'hero.sub': 'MobileMem 通过多阶段流水线构建，覆盖真实用户参与、多模态交互与多源内容。',
      'field.hint': '拖动旋转 · 点击节点',
      'footer.tag': '端侧记忆'
    },
  };

  /* i18n patch (cursurchat-3 v2 rebuild: split titles + figure captions) */
  Object.assign(I18N.en, {
    'ov.title1': 'A memory benchmark for', 'ov.title2': 'real mobile agents',
    'ov.lead': 'A key feature is that these visual content originate from diverse sources, including device cameras, mobile applications, and shared media. This multi-source design ensures that the benchmark reflects the heterogeneous nature of real-world mobile experiences.',
    'card.keme.t': 'KEME synthesis',
    'card.keme.d': 'KEME treats the fragmented user-app sessions as foundational knowledge anchors that reflect what has already occurred and must be preserved.',
    'card.omni.t': 'MobileMem-Omni',
    'card.omni.d': 'MobileMem, featuring real-user participation, multimodal interactions, and multi-source content, is established through a multi-stage pipeline.',
    'card.stats.t': 'Stress-test results',
    'card.stats.d': 'After the filtering process, a total of 19,060 images and 7,415 question-answer pairs are retained in the final benchmark.',
    'ov.figcap': 'As illustrated in Figure, MobileMem, featuring real-user participation, multimodal interactions, and multi-source content, is established through a multi-stage pipeline.',
    'ov.metric.judge': 'Best LLM-Judge',
    'ov.metric.methods': 'Memory methods',
    'ov.metric.backbones': 'Backbones',
    'ov.res.kicker': '§1-§2 · Paper Structure',
    'ov.res.title1': 'Overview of', 'ov.res.title2': 'on-device memory',
    'ov.res.lead': 'Reserved manuscript section.',
    'ov.res.note': 'Reserved for finalized paper text.',
    'reserved.head': 'Reserved manuscript block',
    'reserved.abs.1t': '§1 Introduction',
    'reserved.abs.1d': 'Motivation, challenge framing, and contributions.',
    'reserved.abs.2t': '§2 Overview of On-Device Memory',
    'reserved.abs.2d': 'Definitions, setting, and system-level context.',
    'reserved.abs.3t': '§2.1 Problem Formulation',
    'reserved.abs.3d': 'Task inputs, memory state, queries, and evaluation target.',
    'reserved.syn.1t': 'Formalization and data models',
    'reserved.syn.1d': 'Persona, anchors, trajectories, and QA construction variables.',
    'reserved.syn.2t': 'Closed-loop synthesis',
    'reserved.syn.2d': 'Planner, grounder, realizer, and reviser details.',
    'reserved.syn.3t': 'Hard-distractor analysis',
    'reserved.syn.3d': 'How KEME changes evidence placement and retrieval difficulty.',
    'ov.fig': 'MobileMem as a personal memory agent across everyday mobile scenes.',
    'syn.title1': 'Knowledge-graph-grounded', 'syn.title2': 'memory synthesis',
    'syn.lead': 'KEME treats the fragmented user-app sessions as foundational knowledge anchors that reflect what has already occurred and must be preserved.',
    'syn.fig': 'The overview of the MobileMem synthesis framework.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5 1:1 —5.1 Benchmark Construction) */
  Object.assign(I18N.en, {
    'c1.kicker': '§5.1 · Benchmark Construction', 'c1.t1': 'Built through a', 'c1.t2': 'multi-stage pipeline',
    'c1.lead': 'As illustrated below, MobileMem —featuring real-user participation, multimodal interactions, and multi-source content —is established through a multi-stage pipeline. Specifically, the benchmark includes 16 distinct user trajectories.',
    'c1.fig': 'Figure 1 · The overview of the MobileMem framework.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5 1:1 —5.3 Persona & Memory Modeling) */
  Object.assign(I18N.en, {
    'p2.kicker': '§5.3 · Persona & Memory', 'p2.t1': 'Mobile persona and', 'p2.t2': 'memory modeling',
    'p2.lead': "To balance authenticity, diversity, and scalability, MobileMem constructs personas through a hybrid approach —half derived from representative hired participants, half synthetic —and designs a schema as the core memory structure, organizing each user's persona information, historical status, and temporal milestones.",
    'p2.c1.t': 'Mobile Persona Collection',
    'p2.c1.d': '8 representative hired participants provide real personal information after training on data correctness and privacy; any private data is replaced with same-type fakes to protect privacy.',
    'p2.c2.t': 'Memory Schema',
    'p2.c2.d': "Each persona's schema has three parts: Basic Attributes (core identity), Previous Year's Status (life dimensions), and Previous Year's Milestones (key dates & phases). English and Chinese are the main languages.",
    'p2.c3.t': 'Virtual Personas Generation',
    'p2.c3.d': 'Using real personas as in-context examples, MobileMem generates 8 virtual personas —realistic yet distinct from the references. The full set is the union of real and synthetic personas.',
    'p2.s1': 'Real personas', 'p2.s2': 'Virtual personas', 'p2.s3': 'Schema components', 'p2.s4': 'Main languages',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5 1:1 —5.4 Personal KG Generation) */
  Object.assign(I18N.en, {
    'p3.kicker': '§5.4 · Knowledge Graph', 'p3.t1': 'Personal knowledge', 'p3.t2': 'graph generation',
    'p3.lead': 'Each persona is represented by three components —a basic information vector, an initial state vector, and a personal knowledge graph built from their social relationships.',
    'p3.c1.t': 'Basic Information Vector',
    'p3.c1.d': 'Fundamental traits —identity, personality, life background, and language.',
    'p3.c2.t': 'Initial State Vector',
    'p3.c2.d': 'Location, education, career, health, preferences and other states —the starting point that may shift over time, e.g. relocation, health updates, or preference changes.',
    'p3.c3.t': 'Personal Knowledge Graph',
    'p3.c3.d': 'The persona as the central node with their most significant social contacts as surrounding nodes. Descriptions are enriched by GPT-5.1 and turned into reference photos via the Seedream text-to-image model.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5 1:1 —Synthesis Pipeline, 5 stages merged) */
  Object.assign(I18N.en, {
    'sub.pipe': 'Pipeline',
    'pipe.kicker': '§5.3—.7 · Synthesis Pipeline', 'pipe.t1': 'From persona to', 'pipe.t2': 'evaluable dialogue',
    'pipe.lead': 'A bottom-up, five-stage pipeline turns synthesized personas into a long-horizon multimodal trajectory and evaluable QA —each stage feeds the next.',
    'pipe.s1.t': 'Persona & Memory', 'pipe.s1.d': '8 real + 8 virtual personas, each with a schema of basic attributes, previous-year status and milestones.',
    'pipe.s2.t': 'Knowledge Graph', 'pipe.s2.d': 'Each persona becomes B + S vectors and a social graph G; node photos generated via Seedream.',
    'pipe.s3.t': 'Event Building', 'pipe.s3.d': 'Important dates →a one-year event sequence →step breakdown into ordered sub-events.',
    'pipe.s4.t': 'Dialogue Synthesis', 'pipe.s4.d': 'Event steps →memory points →multimodal sessions with generated images.',
    'pipe.s5.t': 'Question Generation', 'pipe.s5.d': 'Seven question types for systematic memory evaluation.',
    'pipe.fig': 'The five-stage synthesis pipeline of MobileMem.',
    'pipe.s1.long': 'To balance authenticity, diversity, and scalability, MobileMem builds personas through a hybrid approach: half are derived from representative hired participants that reference real participant data, and half are virtual personas generated from those real examples. A unified Schema then organizes basic attributes, previous-year status, and key milestones into the core memory structure —8 real and 8 virtual personas in total.',
    'pipe.s2.long': 'Each persona is represented by three components: a basic information vector B capturing core identity and background, an initial state vector S capturing status and daily patterns before interaction, and a personal knowledge graph G built from social relationships. G centers on the persona, with frequent and significant contacts as surrounding nodes; every node description is enriched by GPT-5.1 and turned into reference photos via the Seedream text-to-image model.',
    'pipe.s3.long': 'Driven by the persona knowledge graph, MobileMem generates the events that form the backbone of each trajectory in three stages: Important Date Collection anchors personally and culturally significant dates; Event Building expands them into a personalized one-year event sequence; and Step Breakdown decomposes every event into temporally ordered sub-event steps, each annotated with the mobile apps and image types involved.',
    'pipe.s4.long': 'Event steps become concrete multimodal dialogues in two phases. Memory Point Decomposition breaks each step into fine-grained textual and visual memory points; Session Generation then lets GPT-5.1 act as an agent to weave them into natural dialogue turns and matching images —produced via HTML rendering, text-to-image, and image-editing tools, with reference photos keeping characters consistent. Sessions are concatenated in temporal order into the full trajectory.',
    'pipe.s5.long': 'To systematically assess memory systems, evaluation questions are built from the generated memory points and step information. They span seven categories: Single-Hop, Multi-Hop, Knowledge Update, Temporal Reasoning, Implicit Preference, Abstention, and Visual Reasoning.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5 —Dataset at a Glance) */
  Object.assign(I18N.en, {
    'sub.stats': 'At a Glance',
    'glance.kicker': '§5 · Dataset at a Glance', 'glance.t1': 'A multimodal benchmark', 'glance.t2': 'built at scale',
    'glance.lead': 'After the filtering process, a total of 19,060 images and 7,415 question-answer pairs are retained in the final benchmark.',
    'glance.n1': 'User trajectories', 'glance.n2': 'Real + virtual personas', 'glance.n3': 'Images', 'glance.n4': 'QA pairs',
    'glance.n5': 'Question types', 'glance.n6': 'Languages (ZH / EN)', 'glance.n7': 'Temporal span', 'glance.n8': 'Image-gen tools',
    'glance.q.h': 'Seven question types',
    'glance.q1': 'Single-Hop', 'glance.q2': 'Multi-Hop', 'glance.q3': 'Knowledge Update', 'glance.q4': 'Temporal Reasoning', 'glance.q5': 'Implicit Preference', 'glance.q6': 'Abstention', 'glance.q7': 'Visual Reasoning',
    'glance.src.h': 'Multi-source & multimodal', 'glance.src1': 'Device cameras', 'glance.src2': 'App screenshots', 'glance.src3': 'Shared media',
    'glance.tools.h': 'Image generation tools', 'glance.tool1': 'HTML rendering', 'glance.tool2': 'Seedream text-to-image', 'glance.tool3': 'Image editing',
    'glance.f1.t': 'Mass generation', 'glance.f1.d': 'GPT-5.1 synthesizes multimodal sessions, images and QA pairs at scale.',
    'glance.f2.t': 'Automatic filtering', 'glance.f2.d': "GPT-5.1 image & question filters, plus ArcFace face verification against each persona's reference photos.",
    'glance.f3.t': 'Manual review →retained', 'glance.f3.d': 'Sample-based human inspection yields the final 19,060 images and 7,415 QA pairs.',
    'glance.qc.h': 'Quality control',
    'glance.fig': 'MobileMem as a lifelong personal memory agent —evolving memory that grasps both the story and its significance.',
    'glance.tools.q': 'For image generation, we employ three types of tools: HTML rendering, text-to-image models, and image editing models. For text-to-image and image-editing models, Seedream is the primary choice; when the generation quality is unsatisfactory, other models are used sequentially as alternatives.',
    'glance.qc.q1': 'To ensure the reliability, we apply quality control procedures to both generated images and evaluation questions. After the filtering process, a total of 19,060 images and 7,415 question-answer pairs are retained in the final benchmark.',
    'glance.qc.q2': "We employ GPT-5.1 as an image filtering agent to assess generated images. For images involving human faces generated by image-editing models, we additionally apply face-recognition tools from the InsightFace library to compare against the persona's initial reference photos, filtering out images below the similarity threshold for same-person identification.",
    'glance.qc.q3': 'We use GPT-5.1 as a question quality agent to automatically evaluate each generated question, checking whether it can be correctly answered based on the source memory points and filtering out questions with unreasonable information or answer errors.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5.2 results tabs) */
  Object.assign(I18N.en, {
    'rtab.t1': 'Main results', 'rtab.t2': 'Caption ablation', 'rtab.t3': 'Language × span', 'rtab.t4': 'Error cases',
    'rtab.q3': 'Memory performance improves as event span increases —short-term events are the most difficult, while longer events yield better results. Meanwhile, a notable gap persists between English and Chinese: most methods score lower on Chinese questions, indicating memory mechanisms remain primarily optimized for English.',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5.2 main results + §5.3 analysis split) */
  Object.assign(I18N.en, {
    'res2.kicker': '§5.2 · Results', 'res2.t1': 'Comparing', 'res2.t2': 'memory methods',
    'ana.kicker': '§5.3 · Analysis', 'ana.t1': 'In-depth', 'ana.t2': 'analysis',
    'ana.b1': 'Captions: a trade-off', 'ana.b2': 'Language × time span', 'ana.b3': 'Common error patterns',
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-3: §5.4 mobile agents —OPPO scenarios) */
  Object.assign(I18N.en, {
    'ag.oppo.h': 'OPPO Application Scenarios',
    'ag.oppo.u1': 'Assess on-device memory middleware across multi-hop, knowledge-update, temporal and visual-reasoning tasks on authentic user trajectories.',
    'ag.oppo.u2': 'Iteratively optimize RAG strategies and memory-management policies with clear, reproducible metrics.',
    'ag.oppo.u3': "Bilingual (English & Chinese) evaluation aligned with OPPO's global market strategy.",
    'ag.oppo.u4': "Seamless integration with OPPO's agent ecosystem —task understanding, safety filters and execution engines —for end-to-end validation.",
  });
  Object.assign(I18N.zh, {});

  /* i18n patch (cursurchat-1: §4 merge —Problem Formulation + KEME accordion + Experiments tabs) */
  Object.assign(I18N.en, {
    'ch4.lead': 'MobileMem is designed to evaluate memory systems in real-world mobile environments.',
    'ch4.t1': 'Design Principle', 'ch4.t1b': 'Formulation',
    'form.kicker': '§4.2 · Problem Formulation', 'form.title': 'Trajectory-QA, formalized',
    'form.lead': 'On-device memory evaluation is formalized as a (trajectory, QA) pair and scored end-to-end.',
    'form.body': 'Each instance is a tuple <b>(T, Q)</b>: <b>T</b> is the user interaction trajectory, <b>Q</b> the associated question-answer set. The trajectory is modeled as a <b>heterogeneous message stream</b> (human-assistant dialogue + app interaction logs), segmented into sessions and flattened into a message sequence.',
    'form.fcap': 'Memory state updates incrementally with each message; T(·) is the timestamp function.',
    'form.flow1': 'Trajectory T = {session} → flattened sequence x',
    'form.flow2': 'Update memory state message by message',
    'form.flow3': 'Answer Q from the final memory state, judged by LLM-as-Judge',
    'form.proto.t': 'End-to-end evaluation protocol',
    'form.proto.d': 'The system ingests messages one by one and updates memory; for each QA pair it answers from the <b>final memory state</b> that integrates the whole trajectory, judged against references by an LLM-as-a-Judge.',
    'keme.x1.h': 'A·plan —Knowledge-Guided Planner', 'keme.x1.d': 'Builds a temporal event graph from the persona root and recursively expands it: coarse life phases →finer sub-event graphs →leaf-level sessions, expanded in topological order.',
    'keme.x2.h': 'A·ground —Knowledge Anchor Grounder', 'keme.x2.d': 'Assigns each anchored app session to a time-compatible event node; when none fits, it revises the graph so every anchor is groundable, propagating a non-contradiction constraint downward.',
    'keme.x3.h': 'A·realize —Experience Realizer', 'keme.x3.d': 'At leaf nodes it adopts or merges anchored content, or synthesizes context-consistent human-assistant dialogue, and drives persona evolution with version-tracked attributes and evidence links.',
    'keme.x4.h': 'A·revise —Experience-Driven Reviser', 'keme.x4.d': 'After each expansion it updates the remaining graph —adding, removing or adjusting future events and edges to resolve inconsistencies and enrich structure, forming a bottom-up feedback loop.',
    'res.kicker': '§4.5 · Experiments & Analysis', 'res.title': 'Even SOTA memory loses to plain RAG',
    'res.lead': 'We conduct our experimental evaluation on the MobileMem benchmark to assess a range of memory management approaches.',
    'res.big': '~49%',
    'res.bigcap': 'The best method (naive RAG) averages only about 49% accuracy —under 50%, far below prior benchmarks like LongMemEval, underscoring how hard heterogeneous multi-source memory is.',
    'res.bigsub': 'backbone: GPT-4o-mini + Qwen3-235B · vs Mem0 / LangMem / A-Mem · retrieved units = 30',
    'res.c1.t': 'Main finding', 'res.c1.d': 'RAG wins on single-hop and relationship questions where direct retrieval suffices; A-Mem overtakes it on multi-hop and summarization thanks to graph-structured memory. All baselines do best on abstention —modern LLMs rarely hallucinate and can flag the unanswerable.',
    'res.c2.t': 'Schema granularity', 'res.c2.d': 'Reducing the 17-dim profile schema to medium (8) and coarse (6): medium and fine beat coarse, yet fine adds little —only about 44% of fine-grained fields are ever mentioned, limited by trajectory length.',
    'res.c3.t': 'Hard-distractor', 'res.c3.d': 'KEME synthesizes answer-preserving but retrieval-harder short trajectories: at top-k=5, RAG drops 40%→0% and EverMemOS 90%→0% —how evidence and distractors are arranged matters more than length.',
  });
  Object.assign(I18N.zh, {});

  /* §4.3 QA synthesis + quality control redesign (cursurchat-4): bottom-up tree + QA/QC columns */
  Object.assign(I18N.en, {
    'ds.kicker': '§4.3 · QA Synthesis & Quality Control',
    'ds.title1': 'From anchored trajectory to', 'ds.title2': 'evaluable QA',
    'ds.lead': 'The entire trajectory construction process can be conceptualized as the generation of a hierarchical tree structure.',
    'ds.tree.rootk': 'ROOT', 'ds.tree.root': 'Cross-session multi-hop QA',
    'ds.tree.mid': 'Combine child QA', 'ds.tree.mid2': 'complex · cross-session',
    'ds.tree.leaf': 'atomic QA',
    'ds.tree.book1': 'Question tool book', 'ds.tree.book2': 'dynamically extended',
    'ds.tree.capt': 'QA examples', 'ds.tree.capd': 'Figure demonstrates some question-answer pairs in MobileMem.',
    'ds.syn.h': 'QA Synthesis',
    'ds.syn.1t': 'Leaf level →atomic QA', 'ds.syn.1d': 'Each leaf generates question-answer pairs from its own trajectory segment.',
    'ds.syn.2t': 'Internal nodes →complex QA', 'ds.syn.2d': 'Each node uses child QA as building blocks to synthesize complex cross-session questions; unused child pairs are sampled and passed upward.',
    'ds.syn.3t': 'Dynamic tool book', 'ds.syn.3d': 'During traversal the agent can extend the question-type tool book with new types on the fly.',
    'ds.qc.h': 'Quality Control',
    'ds.qc.1t': 'Agent spot-checks', 'ds.qc.1d': "Manual spot-checks across agent outputs; KEME's tuned prompts and built-in verification keep quality consistently high.",
    'ds.qc.2t': 'Trajectory refinement', 'ds.qc.2d': 'Overlapping sessions from simultaneous independent events are merged, followed by author-led manual inspection.',
    'ds.qc.3t': 'QA verification', 'ds.qc.3d': 'LLMs verify evidence sufficiency and flag highly similar or redundant questions; low-quality items are rewritten by an LLM.',
    'ds.qc.4t': 'Final manual review', 'ds.qc.4d': 'A final manual inspection eliminates any remaining artifacts to guarantee reliability.',
  });
  Object.assign(I18N.zh, {});

  /* §4.5 experiment tables (cursurchat-4): qualitative + schema + hard-distractor */
  Object.assign(I18N.en, {
    'tbl.method': 'Method', 'tbl.strong': 'Strong at', 'tbl.note': 'Why', 'tbl.allbase': 'All baselines',
    'tbl.lex': 'Lexical ↑', 'tbl.sem': 'Semantic ↑',
    'tbl.coarse': 'Coarse (6)', 'tbl.medium': 'Medium (8)', 'tbl.fine': 'Fine (17)',
    'tbl.single': 'Single', 'tbl.multi': 'Multi', 'tbl.update': 'Update', 'tbl.temporal': 'Temporal',
    'tbl.abst': 'Abst.', 'tbl.pref': 'Pref.', 'tbl.visual': 'Visual', 'tbl.judge': 'Judge',
    'res.tbl1.r1': 'Single-hop · relationship', 'res.tbl1.r1n': 'direct retrieval suffices',
    'res.tbl1.r2': 'Multi-hop · summarization', 'res.tbl1.r2n': 'graph-structured memory',
    'res.tbl1.r3': 'Abstention (best)', 'res.tbl1.r3n': 'modern LLMs detect unanswerable',
    'tbl.schema': 'Profile Schema', 'tbl.traj': 'Trajectory',
    'res.tbl3.r1': 'LongMemEval (original)', 'res.tbl3.r2': 'KEME (synthesized)',
    'res.tbl3.note': 'Shorter KEME trajectories make retrieval harder while preserving answers —evidence layout matters more than length.',
  });
  Object.assign(I18N.zh, {});

  /* §4.5 academic polish (cursurchat-4): neutral title + setup card + table captions */
  Object.assign(I18N.en, {
    'res.title': 'Hard-distractor synthesis with KEME',
    'res.lead': 'We further evaluate whether KEME can synthesize answer-preserving but retrieval-harder trajectories.',
    'res.schema.note': 'Medium- and fine-grained schemas outperform the coarse-grained schema, while fine-grained brings limited gains over reduced variants.',
    'res.hard.lead': 'Despite shorter trajectories, retrieval becomes significantly harder: RAG drops from 40.00% to 20.00% at top-k=5, and EverMemOS drops from 90.00% to 80.00%.',
    'exp.setup.h': 'Experimental setup',
    'exp.setup.bk': 'Backbones', 'exp.setup.me': 'Methods', 'exp.setup.rt': 'Retrieval', 'exp.setup.mt': 'Metric',
    'exp.setup.key': 'The best method (naive RAG) averages ≈9% —under 50%, far below prior benchmarks, underscoring the difficulty of heterogeneous, multi-source memory.',
    'tbl.cap1': 'Table 1 · Method strengths across question types (qualitative).',
    'tbl.cap2': 'Table 2 · Trajectory diversity under profile-schema granularity.',
    'tbl.cap3': 'Table 3 · Hard-distractor —accuracy (%) on original vs. KEME-synthesized trajectories.',
    'tbl.system': 'Memory system', 'tbl.original': 'Original', 'tbl.kemeSynth': 'KEME', 'tbl.delta': 'Drop',
    'tbl.rag': 'Naive RAG', 'tbl.ever': 'EverMemOS',
    'ds.tree.capt': 'QA examples', 'ds.tree.capd': 'Figure demonstrates some question-answer pairs in MobileMem.',
    'fig.hdl.t': 'Trajectory length', 'fig.hdl.d': 'length distribution of KEME hard-distractor trajectories.',
    'fig.hdr.t': 'Evidence rank', 'fig.hdr.d': 'KEME pushes answer-supporting evidence toward less favorable retrieval ranks.',
    'fig.hard.a': '(a) Average performance across two memory systems on LongMemEval and KEME',
    'fig.hard.b': '(b) Trajectory length distribution',
    'fig.hard.c': '(c) Source evidence rank analysis',
    'res.hard.p1': 'Starting from LongMemEval, we select 10 questions (5 easy, 5 challenging), retain their evidence sessions, and use GPT-5.2 to generate compatible medium-grained profiles and difficulty-enhancing guidelines.',
    'res.hard.p2': 'We modify only the global system prompt of KEME and generate trajectories with m_max=10 using GPT-5.1. All outputs are manually verified to preserve correct answers.',
    'res.hard.p3': 'As shown in Figure, despite shorter trajectories, retrieval becomes significantly harder: RAG drops from 40.00% to 20.00% at top-k=5, and EverMemOS drops from 90.00% to 80.00%. More broadly, this suggests that, in this setting, how evidence and distractors are arranged in the trajectory can be more influential than trajectory length alone, highlighting the ability of KEME to synthesize short but hard trajectories.',
    'res.hard.p4': 'A representative failure occurs on question 50635ada, where the correct answer is Premier Silver. Although EverMemOS stores relevant memories, retrieval fails to recover precise evidence. Retrieved results are dominated by semantically similar but vague or irrelevant entries, which mislead retrieval and prevent correct reasoning.',
  });
  Object.assign(I18N.zh, {});

  /* Chinese academic translation pass: faithful to manuscript wording, replacing English fallbacks. */
  Object.assign(I18N.zh, {});

  /* User edit export: "不要了" means hide this text node, not render the words. */
  Object.assign(I18N.zh, {});

  /* Final overview pass: make the first screen a paper-structure index. */
  Object.assign(I18N.en, {
    'nav.abstract': 'Overview',
    'nav.dataset': 'MobileMem Dataset',
    'nav.omni': 'MobileMem-Omni Dataset',
    'ov.title1': 'Reserved for',
    'ov.title2': 'paper-aligned content',
    'ov.lead': 'This overview area is intentionally left open and will be filled after the corresponding LaTeX manuscript sections are synchronized.',
    'card.keme.t': 'Reserved section',
    'card.keme.d': 'Content will be added here after the corresponding LaTeX manuscript section is synchronized.',
    'card.omni.t': 'Reserved section',
    'card.omni.d': 'Content will be added here after the corresponding LaTeX manuscript section is synchronized.',
    'card.stats.t': 'Reserved section',
    'card.stats.d': 'Content will be added here after the corresponding LaTeX manuscript section is synchronized.',
    'ov.placeholder': 'Reserved for manuscript figure',
    'entry.mobilemem.title': 'MobileMem Dataset',
    'entry.omni.title': 'MobileMem-Omni Dataset',
    'entry.mobilemem': 'View MobileMem Dataset',
    'entry.omni': 'View MobileMem-Omni Dataset'
  });
  Object.assign(I18N.zh, {
    'nav.abstract': '概览',
    'nav.dataset': 'MobileMem 数据集',
    'nav.omni': 'MobileMem-Omni Dataset',
    'ov.title1': '预留用于论文同步内容',
    'ov.title2': '',
    'ov.lead': '该概览区域暂作留白，待对应 LaTeX 论文段落同步后填充。',
    'card.keme.t': '预留内容区',
    'card.keme.d': '待对应 LaTeX 论文段落同步后，在此补充展示内容。',
    'card.omni.t': '预留内容区',
    'card.omni.d': '待对应 LaTeX 论文段落同步后，在此补充展示内容。',
    'card.stats.t': '预留内容区',
    'card.stats.d': '待对应 LaTeX 论文段落同步后，在此补充展示内容。',
    'ov.placeholder': '预留论文图位',
    'entry.mobilemem.title': 'MobileMem 数据集',
    'entry.omni.title': 'MobileMem-Omni Dataset',
    'entry.mobilemem': '查看 MobileMem 数据集',
    'entry.omni': '查看 MobileMem-Omni Dataset'
  });

  /* Chinese UI coverage for the current index.html surface. */
  Object.assign(I18N.zh, {
    'ch4.t2': 'KEME 框架',
    'ch4.t3': '问答合成与质量控制',
    'ch4.t4': '实验与分析',
    'sub.build': '基准构建',
    'sub.stats': '规模一览',
    'sub.results': '主结果',
    'sub.analysis': '分析',
    'hero.badge': '预印本 · OPPO × OpenKG',
    'hero.affil': 'OPPO · OpenKG',
    'cta.paper': '论文',
    'cta.code': '</>代码',
    'cta.data': '◈数据集',
    'cta.results': '邮箱',
    'ov.kicker': '概览',
    'syn.kicker': '§3 · 记忆合成',
    'syn.title1': '知识图谱驱动的端侧记忆合成',
    'syn.title2': '',
    'syn.lead': 'KEME 将零散的用户-App 会话作为知识锚点，并将其组织为连贯、可持续演化的长期轨迹。',
    'reserved.head': '预留论文内容块',
    'reserved.syn.1t': '知识锚点',
    'reserved.syn.1d': '保留已发生且必须一致的用户-App 会话片段。',
    'reserved.syn.2t': '轨迹扩展',
    'reserved.syn.2d': '围绕人物画像和事件图生成多会话经历。',
    'reserved.syn.3t': '经验修订',
    'reserved.syn.3d': '根据新生成经验更新后续事件和人物状态。',
    'syn.note': '预留给论文定稿后的补充文字。',
    'keme.kicker': '核心框架',
    'keme.title': 'KEME：知识引导的经验合成',
    'keme.lead': 'KEME 将零散的用户-App 会话作为基础知识锚点，再分层合成为连贯、持续演化的长程轨迹。',
    'fig.keme.t': 'KEME 框架',
    'fig.keme.d': '以锚定知识和经验为驱动的闭环轨迹合成示意。',
    'keme.x1.h': 'A·plan — 知识引导规划器',
    'keme.x1.d': '从人物画像根节点构建时序事件图，并递归展开：粗粒度生活阶段 → 更细子事件图 → 叶级会话。',
    'keme.x2.h': 'A·ground — 知识锚点锚定器',
    'keme.x2.d': '将每个已锚定的 App 会话分配到时间兼容的事件节点；若无法匹配，则修订事件图，保证锚点可落地。',
    'keme.x3.h': 'A·realize — 经验实现器',
    'keme.x3.d': '在叶节点采纳或合并锚定内容，或合成上下文一致的人机对话，并通过版本化属性和证据链接驱动人物画像演化。',
    'keme.x4.h': 'A·revise — 经验驱动修订器',
    'keme.x4.d': '每次展开后更新剩余事件图，增删或调整未来事件与边，以消除不一致并丰富结构。',
    'ds.kicker': '§4.3 · 问答合成与质量控制',
    'ds.title1': '从锚定轨迹到可评测问答',
    'ds.title2': '',
    'ds.lead': '整个轨迹构建过程可被概念化为层次树结构的生成。',
    'ds.syn.h': '问答合成',
    'ds.syn.1t': '叶节点 → 原子问答',
    'ds.syn.1d': '在每个叶节点，智能体基于对应轨迹片段生成问答对。',
    'ds.syn.2t': '内部节点 → 复杂问答',
    'ds.syn.2d': '内部节点以子节点问答为构件合成复杂跨会话问题；未使用的子问答被采样并继续向上传递。',
    'ds.syn.3t': '动态问题工具书',
    'ds.syn.3d': '合成过程中，智能体可以动态扩展问题工具书并加入新的问题类型。',
    'ds.qc.h': '质量控制',
    'ds.qc.1t': '人工抽检',
    'ds.qc.1d': '首先对不同智能体的输出进行人工抽检；受益于精细调优的提示词和 KEME 内置自动校验，生成质量保持稳定。',
    'ds.qc.2t': '轨迹精修',
    'ds.qc.2d': '进一步合并由同时发生的独立事件造成的重叠会话，并由作者进行人工检查。',
    'ds.qc.3t': '问答校验',
    'ds.qc.3d': '利用大语言模型验证支撑证据是否充分，并识别与既有问答高度相似的问题；低质量或冗余样本由大语言模型重写。',
    'ds.qc.4t': '最终人工检查',
    'ds.qc.4d': '最后通过人工检查消除潜在瑕疵，以保证数据可靠性。',
    'ds.tree.capt': '问答案例',
    'ds.tree.capd': '图中展示了 MobileMem 中的部分问答对。',
    'res.kicker': '§4.5 · 实验与分析',
    'res.title': 'KEME 的困难干扰项合成',
    'res.lead': '我们进一步评估 KEME 是否能够合成答案保持不变、但检索更困难的轨迹。',
    'fig.hard.a': '（a）两个记忆系统在 LongMemEval 与 KEME 上的平均表现',
    'fig.hard.b': '（b）轨迹长度分布',
    'fig.hard.c': '（c）源证据排名分析',
    'res.c3.t': '困难干扰项合成',
    'res.hard.p1': '从 LongMemEval 出发，我们选择 10 个问题（5 个简单、5 个困难），保留其证据会话，并使用 GPT-5.2 生成兼容的中粒度画像和增强难度的指导。',
    'res.hard.p2': '我们仅修改 KEME 的全局系统提示，并使用 GPT-5.1 以 m_max=10 生成轨迹；所有输出均经人工验证以保持答案正确。',
    'res.hard.p3': '如图所示，尽管轨迹更短，检索却显著变难：RAG 在 top-k=5 下从 40.00% 降至 20.00%，EverMemOS 从 90.00% 降至 80.00%。',
    'res.hard.p4': '一个代表性失败案例是问题 50635ada，正确答案为 Premier Silver；相关记忆虽被存储，但检索未能找回精确证据。',
    'c1.kicker': '§5.1 · 基准构建',
    'c1.t1': '通过多阶段流水线构建',
    'c1.t2': '',
    'c1.lead': '如图所示，MobileMem 以真实用户参与、多模态交互和多源内容为特征，通过多阶段流水线构建。具体而言，该基准包含 16 条不同用户轨迹。',
    'pipe.s1.t': '人物画像与记忆',
    'pipe.s1.long': '为平衡真实性、多样性与可扩展性，MobileMem 采用混合方式构建人物画像：一半来自代表性受雇参与者并参考真实参与者数据，另一半由这些真实样例生成虚拟画像。统一 Schema 进一步组织基础属性、上一年状态和关键里程碑，形成核心记忆结构。',
    'pipe.s2.t': '知识图谱',
    'pipe.s2.long': '每个人物画像由三部分表示：基础信息向量 B、初始状态向量 S，以及由社会关系构建的个人知识图谱 G。G 以人物为中心，周围节点为频繁且重要的联系人，并通过 GPT-5.1 丰富描述，再由 Seedream 生成参考照片。',
    'pipe.s3.t': '事件构建',
    'pipe.s3.long': '在人物知识图谱驱动下，MobileMem 分三阶段生成构成轨迹主干的事件：重要日期收集、事件构建和步骤拆解。',
    'pipe.s4.t': '对话合成',
    'pipe.s4.long': '事件步骤被转化为具体的多模态对话。记忆点拆解将每个步骤拆为细粒度文本与视觉记忆点；会话生成再将其织入自然对话轮次和匹配图像。',
    'pipe.s5.t': '问题生成',
    'pipe.s5.long': '为系统评估记忆能力，评测问题基于生成的记忆点和步骤信息构建，覆盖单跳、多跳、知识更新、时间推理、隐式偏好、拒答和视觉推理七类。',
    'c1.fig': 'MobileMem 框架总览。',
    'glance.kicker': '§5 · 规模一览',
    'glance.t1': '大规模构建的多模态基准',
    'glance.t2': '',
    'glance.fig': 'MobileMem 作为长期个人记忆智能体，既把握故事本身，也理解其意义。',
    'glance.q.h': '七类问题',
    'glance.src.h': '多源与多模态',
    'glance.tools.h': '图像生成工具',
    'glance.tools.q': '图像生成使用三类工具：HTML 渲染、文生图模型和图像编辑模型。文生图和图像编辑主要采用 Seedream；当生成质量不足时，再依次使用其他模型作为替代。',
    'glance.qc.h': '质量控制',
    'glance.qc.q1': '为确保可靠性，我们同时对生成图像和评测问题执行质量控制。过滤后，最终基准保留 19,060 张图像和 7,415 个问答对。',
    'glance.qc.q2': '我们使用 GPT-5.1 作为图像过滤智能体评估生成图像。对于图像编辑模型生成且包含人脸的图像，额外使用 InsightFace 与人物初始参考照进行比对，过滤低于同人识别相似度阈值的图像。',
    'glance.qc.q3': '我们使用 GPT-5.1 作为问题质量智能体自动评估每个生成问题，检查其是否能基于源记忆点正确回答，并过滤信息不合理或答案错误的问题。',
    'glance.n1': '用户轨迹',
    'glance.n3': '图像',
    'glance.n4': '问答对',
    'glance.n5': '问题类型',
    'omni.s4.q2': '为系统评估记忆系统表现，我们基于生成的记忆点和步骤信息构建评测问题，覆盖七个预定义类别：单跳、多跳、知识更新、时间推理、隐式偏好、拒答和视觉推理。',
    'omni.s1.q3': '视觉内容来自设备相机、移动应用和共享媒体等多种来源，反映真实移动体验中的异构性；基准同时支持多语种交互，要求记忆系统保持跨语言一致性。',
    'res2.kicker': '§5.2 · 结果',
    'res2.t1': '比较记忆方法',
    'res2.t2': '',
    'omni.s5.q1': '如表所示，不同方法家族之间呈现清晰的性能层级。专用记忆增强框架在几乎所有任务和骨干模型上都稳定优于长上下文和 RAG 类方法。',
    'tbl.textual': '文本记忆方法',
    'tbl.multimodal': '多模态记忆方法',
    'tbl.method': '方法',
    'tbl.single': '单跳',
    'tbl.multi': '多跳',
    'tbl.update': '更新',
    'tbl.temporal': '时间',
    'tbl.abst': '拒答',
    'tbl.pref': '偏好',
    'tbl.visual': '视觉',
    'tbl.judge': 'Judge',
    'tbl.gpt': 'GPT-5.4-mini',
    'tbl.qwen': 'Qwen3-VL-8B-Instruct',
    'omni.tbl.cap': '各方法问答表现。每个任务的分数均使用 LLM-as-a-Judge 评估。',
    'ana.kicker': '§5.3 · 分析',
    'ana.t1': '深入分析',
    'ana.t2': '',
    'ana.b1': '图像描述：一种权衡',
    'omni.s5.q2': '如图所示，将图像描述加入 NaiveRAG 会形成权衡：视觉推理问题表现提升，但文本导向问题表现下降。',
    'omni.s5.fig1': 'NaiveRAG 的 LLM-Judge 表现变化：图像描述提升视觉推理，但削弱其他文本导向问题。',
    'ana.b2': '语言 × 时间跨度',
    'rtab.q3': '随着事件跨度增加，记忆表现有所提升：短期事件最困难，较长事件表现更好。同时，中英文之间仍存在明显差距，多数方法在中文问题上得分更低，说明现有记忆机制仍主要针对英文优化。',
    'omni.s5.fig2': '事件类型 LLM-Judge 表现雷达图。事件按交互语言（中文、英文）和事件跨度（短期、中期、长期）划分。',
    'ana.b3': '常见错误模式',
    'omni.s5.q3': '如图所示，我们展示不同方法中的常见错误。多模态记忆方法容易检索到与目标同类型但与真实答案无关的图像，从而生成错误记忆。',
    'omni.s5.fig3': '案例分析。（a）为包含正确答案的对话，（b）（c）（d）展示记忆方法产生错误记忆的信息来源。',
    'bib.kicker': '引用',
    'bib.title': 'BibTeX',
    'bib.todo': '作者列表和发表信息待定。',
    'bib.copy': '复制',
    'team.kicker': '机构',
    'team.title': '合作机构',
    'team.eyebrow': '本工作由以下机构联合完成',
    'team.views': '页面浏览',
    'team.note': 'MobileMem 由 OPPO 与 OpenKG 联合开发。'
  });

  /* User edit sync: "不要了" marks positions where adding text is redundant. */
  Object.assign(I18N.en, {
    'hero.badge': '',
    'hero.affil': '',
    'cta.code': 'Code'
  });
  Object.assign(I18N.zh, {
    'hero.badge': '',
    'hero.affil': '',
    'cta.code': '代码',
    'c1.t2': '',
    'glance.t2': '',
    'res2.t2': ''
  });

  const params = new URLSearchParams(window.location.search);
  const requestedLang = params.get('lang');
  let lang = requestedLang === 'zh' || requestedLang === 'en' ? requestedLang : 'en';
  const stripMarkup = (s) => {
    const div = document.createElement('div');
    div.innerHTML = String(s || '');
    return (div.textContent || '').trim();
  };
  const shouldHideText = (s) => stripMarkup(s) === '不要了';
  const HIDDEN_I18N_KEYS = new Set(
    Object.keys(I18N.zh).filter((k) => shouldHideText(I18N.zh[k]))
  );
  const shouldHideI18n = (k, value) => HIDDEN_I18N_KEYS.has(k) || shouldHideText(value);

  const applyLang = (l) => {
    lang = l;
    document.documentElement.lang = l === 'zh' ? 'zh-CN' : 'en';
    document.title = l === 'zh' ? 'MobileMem · 端侧记忆基准' : 'MobileMem - On-Device Memory Benchmark';
    const d = I18N[l] || I18N.en;
    $$('[data-i18n]').forEach((el) => {
      const k = el.dataset.i18n;
      const hasValue = Object.prototype.hasOwnProperty.call(d, k);
      const value = hasValue ? d[k] : '';
      if (shouldHideI18n(k, value)) {
        el.hidden = true;
        return;
      }
      if (!hasValue) return;
      if (value === '') {
        el.hidden = true;
        return;
      }
      el.hidden = false;
      if (k === 'orbit.core') el.innerHTML = value.replace('\n', '<br/>');
      else if (value.includes('<')) el.innerHTML = value;
      else el.textContent = value;
    });
    if (window.__memRefresh) window.__memRefresh();
  };

  $('#langToggle')?.addEventListener('click', () => applyLang(lang === 'en' ? 'zh' : 'en'));

  /* Inline edit mode: click text to edit, export edits as JSON. */
  const editToggle = $('#editToggle');
  const exportBtn = $('#exportEdits');
  let editMode = false;
  const editEls = () => $$('main [data-i18n]');
  if (editToggle) {
    const hint = document.createElement('div');
    hint.className = 'edit-hint';
    hint.textContent = 'EDIT MODE · click any text to edit · Export to save';
    document.body.appendChild(hint);
    editToggle.addEventListener('click', () => {
      editMode = !editMode;
      document.body.classList.toggle('edit-mode', editMode);
      editToggle.classList.toggle('is-on', editMode);
      editToggle.textContent = editMode ? 'Done' : 'Edit';
      editEls().forEach((el) => {
        if (editMode) el.setAttribute('contenteditable', 'true');
        else el.removeAttribute('contenteditable');
      });
    });
  }
  exportBtn?.addEventListener('click', () => {
    const data = {};
    editEls().forEach((el) => { data[el.dataset.i18n] = el.innerHTML.trim(); });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `mem-edits-${lang}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  });

  /* Mobile menu */
  const drawer = $('#mobileDrawer');
  const menuBtn = $('#menuBtn');
  menuBtn?.addEventListener('click', () => {
    const open = drawer.classList.toggle('is-open');
    drawer.setAttribute('aria-hidden', String(!open));
  });
  $$('#mobileDrawer a').forEach((a) => a.addEventListener('click', () => {
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
  }));

  const gateForSection = {
    keme: 'mobilemem',
    dataset: 'mobilemem',
    results: 'mobilemem',
    'omni-overview': 'omni',
    'omni-stats': 'omni',
    'omni-results': 'omni',
    'omni-analysis': 'omni',
  };
  const entrySections = new Set(['mobilemem-entry', 'omni-entry']);
  const gateGroups = ['mobilemem', 'omni'];
  const closeGates = () => {
    gateGroups.forEach((gate) => document.body.classList.remove(`gate-${gate}-open`));
  };
  const openGate = (gate) => {
    if (!gate) return;
    document.body.classList.add(`gate-${gate}-open`);
  };
  const syncGateForTarget = (id) => {
    if (entrySections.has(id)) {
      closeGates();
      return;
    }
    const gate = gateForSection[id];
    if (!gate) return;
    closeGates();
    openGate(gate);
  };

  $$('[data-entry-target]').forEach((a) => {
    a.addEventListener('click', (e) => {
      const id = a.dataset.entryTarget;
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      e.preventDefault();
      closeGates();
      openGate(a.dataset.entryGate || gateForSection[id]);
      requestAnimationFrame(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      history.pushState(null, '', `#${id}`);
      setTimeout(() => {
        flushReveal();
        onScroll();
        window.dispatchEvent(new Event('hashchange'));
      }, 120);
    });
  });
  const alignHashTarget = () => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    syncGateForTarget(id);
    const target = id ? document.getElementById(id) : null;
    if (target) target.scrollIntoView({ behavior: 'auto', block: 'start' });
  };
  if (window.location.hash) {
    requestAnimationFrame(alignHashTarget);
    window.addEventListener('load', alignHashTarget, { once: true });
  }
  window.addEventListener('hashchange', () => requestAnimationFrame(alignHashTarget));

  /* Page views: load the counter only on public hosts, without any local offset. */
  const pageViewScript = document.querySelector('[data-page-view-script]');
  const isLocalPreview = ['localhost', '127.0.0.1', '::1', ''].includes(window.location.hostname);
  if (pageViewScript && !isLocalPreview) {
    const script = document.createElement('script');
    script.async = true;
    script.src = pageViewScript.dataset.pageViewScript;
    document.body.appendChild(script);
  }

  /* Scroll progress + nav */
  const progress = $('#scrollProgress');
  const nav = $('#siteNav');
  const sections = $$('section[id]');
  const navLinks = $$('#navLinks a, #mobileDrawer a');
  /* Top nav: map every section to one of the 4 chapters */
  const sectionNav = {
    highlights: 'highlights',
    'mobilemem-entry': 'mobilemem-entry',
    formulation: 'mobilemem-entry', keme: 'mobilemem-entry', dataset: 'mobilemem-entry', results: 'mobilemem-entry',
    'omni-entry': 'omni-entry',
    'omni-scene': 'omni-entry', 'omni-layer': 'omni-entry', 'omni-pda': 'omni-entry',
    'omni-overview': 'omni-entry', 'omni-stats': 'omni-entry', 'omni-persona': 'omni-entry', 'omni-events': 'omni-entry',
    'omni-synthesis': 'omni-entry', 'omni-results': 'omni-entry', 'omni-analysis': 'omni-entry',
    team: 'omni-entry',
  };

  /* dual sub-nav: §4 and §5 swap into the top bar while their real content sections are in view */
  const navSub4 = $('#navSub4');
  const navSub5 = $('#navSub5');
  const sub4Links = $$('#navSub4 a:not(.subnav__home)');
  const sub5Links = $$('#navSub5 a:not(.subnav__home)');
  const sub4Ids = ['keme', 'dataset', 'results'];
  const sub5Map = {
    'omni-overview': 'omni-overview', 'omni-stats': 'omni-stats',
    'omni-results': 'omni-results', 'omni-analysis': 'omni-analysis',
  };

  const onScroll = () => {
    const y = window.scrollY;
    const h = document.documentElement.scrollHeight - window.innerHeight;
    if (progress) progress.style.width = `${(y / Math.max(h, 1)) * 100}%`;
    nav?.classList.toggle('is-scrolled', y > 40);

    let current = 'highlights';
    sections.forEach((s) => {
      if (!s.getClientRects().length) return;
      if (s.getBoundingClientRect().top <= 120) current = sectionNav[s.id] || current;
    });
    navLinks.forEach((a) => {
      const href = a.getAttribute('href')?.slice(1);
      a.classList.toggle('is-active', href === current);
    });

    /* dual sub-nav swap: §4 then §5 take over the top bar while in view */
    const ch4El = document.getElementById('keme');
    const omniEl = document.getElementById('omni-overview');
    const endEl = document.getElementById('team');
    const TH = 140;
    const sectionTop = (el) => (el && el.getClientRects().length ? el.getBoundingClientRect().top : Infinity);
    const t4 = sectionTop(ch4El);
    const t5 = sectionTop(omniEl);
    const tEnd = sectionTop(endEl);
    const in4 = t4 <= TH && t5 > TH;
    const in5 = t5 <= TH && tEnd > TH;
    nav?.classList.toggle('is-sub', in4 || in5);
    if (navSub4) { navSub4.classList.toggle('is-on', in4); navSub4.setAttribute('aria-hidden', String(!in4)); }
    if (navSub5) { navSub5.classList.toggle('is-on', in5); navSub5.setAttribute('aria-hidden', String(!in5)); }
    if (in4) {
      let cur = 'keme';
      sub4Ids.forEach((id) => { const el = document.getElementById(id); if (el && el.getClientRects().length && el.getBoundingClientRect().top <= 160) cur = id; });
      sub4Links.forEach((a) => a.classList.toggle('is-active', a.getAttribute('href')?.slice(1) === cur));
    }
    if (in5) {
      let cur = 'omni-overview';
      sections.forEach((s) => { if (sub5Map[s.id] && s.getClientRects().length && s.getBoundingClientRect().top <= 160) cur = sub5Map[s.id]; });
      sub5Links.forEach((a) => a.classList.toggle('is-active', a.getAttribute('href')?.slice(1) === cur));
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* Reveal */
  const revealIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add('is-visible');
        revealIO.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
  const flushReveal = () => {
    $$('.reveal:not(.is-visible)').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.96 && r.bottom > 0) {
        el.classList.add('is-visible');
        revealIO.unobserve(el);
      }
    });
  };
  $$('.reveal').forEach((el) => revealIO.observe(el));
  requestAnimationFrame(flushReveal);
  window.addEventListener('load', flushReveal);
  window.addEventListener('hashchange', () => setTimeout(flushReveal, 80));

  /* Count-up */
  const countIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.querySelectorAll('[data-count]').forEach((el) => {
        const target = parseFloat(el.dataset.count);
        const suffix = el.dataset.suffix || '';
        const dur = 1400;
        const start = performance.now();
        const tick = (now) => {
          const p = Math.min((now - start) / dur, 1);
          const v = Math.round(target * (1 - Math.pow(1 - p, 3)));
          el.textContent = v.toLocaleString('en-US') + suffix;
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      countIO.unobserve(e.target);
    });
  }, { threshold: 0.3 });
  $$('.stats-strip').forEach((el) => countIO.observe(el));

  /* Accordion: exclusive —only one panel open at a time */
  $$('.accordion--omni').forEach((accordion) => {
    const items = $$('.acc-item', accordion);
    items.forEach((item) => {
      item.addEventListener('toggle', () => {
        if (item.open) items.forEach((el) => { if (el !== item) el.open = false; });
      });
    });
  });

  /* §4 experiments: text tabs */
  $$('.t4-tabs').forEach((wrap) => {
    const btns = $$('.t4-tabs__btn', wrap);
    const panels = $$('.t4-tabs__panel', wrap);
    btns.forEach((btn, i) => btn.addEventListener('click', () => {
      btns.forEach((b) => b.classList.remove('is-active'));
      panels.forEach((p) => p.classList.remove('is-active'));
      btn.classList.add('is-active');
      panels[i].classList.add('is-active');
    }));
  });

  /* §5.1 synthesis pipeline: content panel + bottom step keys */
  const pcar = $('.pcar');
  if (pcar) {
    const dots = $$('.pcar__dot', pcar);
    const panels = $$('.pcar__panel', pcar);
    const set = (n) => {
      dots.forEach((d) => d.classList.toggle('is-active', d.dataset.step === n));
      panels.forEach((p) => p.classList.toggle('is-active', p.dataset.step === n));
    };
    dots.forEach((d) => d.addEventListener('click', () => set(d.dataset.step)));
  }

  /* §5.2 results tabs: button-switched table / figures */
  const rtabs = $('.rtabs');
  if (rtabs) {
    const btns = $$('.rtab-btn', rtabs);
    const panels = $$('.rtab-panel', rtabs);
    const setR = (n) => {
      btns.forEach((b) => b.classList.toggle('is-active', b.dataset.rtab === n));
      panels.forEach((p) => p.classList.toggle('is-active', p.dataset.rtab === n));
    };
    btns.forEach((b) => b.addEventListener('click', () => setR(b.dataset.rtab)));
  }

  /* §5.2 secondary toggle: textual vs multimodal method tables */
  $$('.rsub-nav').forEach((nav) => {
    const scope = nav.parentElement;
    const sbtns = $$('.rsub-btn', nav);
    const spanels = $$('.rsub-panel', scope);
    const setS = (k) => {
      sbtns.forEach((sb) => sb.classList.toggle('is-active', sb.dataset.rsub === k));
      spanels.forEach((sp) => sp.classList.toggle('is-active', sp.dataset.rsub === k));
    };
    sbtns.forEach((sb) => sb.addEventListener('click', () => setS(sb.dataset.rsub)));
  });

  /* Copy bibtex */
  $('#copyBib')?.addEventListener('click', async () => {
    const code = $('#bibCode')?.textContent || '';
    try {
      await navigator.clipboard.writeText(code);
      const btn = $('#copyBib');
      btn.classList.add('is-copied');
      const orig = btn.textContent;
      btn.textContent = lang === 'zh' ? '已复制' : 'Copied!';
      setTimeout(() => { btn.classList.remove('is-copied'); btn.textContent = orig; }, 2000);
    } catch (_) { /* noop */ }
  });

  /* Lightbox for figures */
  const lb = $('#lightbox');
  const lbImg = $('#lightboxImg');
  const closeLightbox = () => {
    lb?.classList.remove('is-open');
    lb?.setAttribute('aria-hidden', 'true');
  };
  $$('.paper-fig__media[data-zoom]').forEach((m) => {
    m.addEventListener('click', () => {
      if (!lb || !lbImg) return;
      const img = m.querySelector('img');
      lbImg.src = m.dataset.zoom;
      lbImg.alt = img ? img.alt : '';
      lb.classList.add('is-open');
      lb.setAttribute('aria-hidden', 'false');
    });
  });
  $('#lightboxClose')?.addEventListener('click', closeLightbox);
  lb?.addEventListener('click', closeLightbox);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLightbox(); });

  /* 鈹€鈹€ Interactive 3D memory field (hero) 鈹€鈹€ */
  /* uid0 folder →node image mapping (assets/media/nodes/) */
  const memoryPersonas = {
    uid0: [
      { core: true, zh: '用户画像', en: 'PERSONA CORE', dzh: '由基础属性、初始状态与社交知识图谱构成，是长期移动记忆的中心锚点，属于文字与结构化属性模态。', den: 'Basic attributes, initial states, and a social knowledge graph form the central anchor of long-term mobile memory as text and structured attributes.' },
      { img: 'assets/media/nodes/persona.png', zh: '画像参考照', en: 'PERSONA REFERENCES', dzh: '依据画像的年龄、性别、国籍等基础属性生成，用于固定用户外观。', den: 'Reference photos generated from persona attributes such as age, gender, nationality, and appearance.' },
      { img: 'assets/media/nodes/family.png', zh: '社交联系人照', en: 'KG PERSON REFERENCES', dzh: '为知识图谱中的重要联系人生成参考照片，保持人物节点的视觉一致性。', den: 'Reference photos for important social contacts in the persona knowledge graph.' },
      { img: 'assets/media/nodes/photos.png', zh: '相机照片', en: 'CAMERA PHOTOS', dzh: '把用户与联系人放入具体事件场景，模拟真实手机相册中的私人照片。', den: 'Event-grounded private photos that place the persona and contacts into concrete scenes.' },
      { img: 'assets/media/nodes/books.png', zh: '阅读平台', en: 'BOOK PLATFORMS', dzh: '通过 HTML 模板生成电子书界面，包含书名、作者、阅读进度等信息。', den: 'Rendered e-book platform screenshots with titles, authors, and reading progress.' },
      { img: 'assets/media/nodes/music.png', zh: '音乐平台', en: 'MUSIC PLATFORMS', dzh: '模拟播放页、歌单和音乐偏好，将听歌记录转化为可检索视觉记忆。', den: 'Music app screens such as playback pages and playlists, grounding listening preferences.' },
      { img: 'assets/media/nodes/events.png', zh: '视频平台', en: 'VIDEO PLATFORMS', dzh: '生成视频封面与播放平台元数据，如标题、上传者、播放量和点赞数。', den: 'Video-platform screenshots with covers, titles, uploader metadata, views, and likes.' },
      { img: 'assets/media/nodes/payments.png', zh: '交易记录', en: 'TRANSACTION RECORDS', dzh: '覆盖账单、转账和消费流水，为金额、商户和支付方式提供证据。', den: 'Bills, transfers, and payment records that preserve merchants, amounts, and payment methods.' },
      { img: 'assets/media/nodes/travel.png', zh: '票务记录', en: 'TICKET RECORDS', dzh: '包含航班、火车、演出或景点票据，锚定行程与预约类事件。', den: 'Flight, train, venue, or attraction tickets that anchor trips and reservations.' },
      { img: 'assets/media/nodes/preference.png', zh: '购物记录', en: 'SHOPPING RECORDS', dzh: '模拟电商订单、商品页和购物偏好，记录品牌、价格与购买决策。', den: 'E-commerce orders and product pages that capture brands, prices, and purchase choices.' },
      { img: 'assets/media/nodes/chats.png', zh: '社媒聊天记录', en: 'SOCIAL CHAT RECORDS', dzh: '以群聊和私聊截图保存参与者、消息序列与跨 App 对话上下文。', den: 'Group or direct-message screenshots with participants, message sequences, and context.' },
      { img: 'assets/media/nodes/timeline.png', zh: '社媒动态', en: 'SOCIAL POSTS', dzh: '朋友圈、动态和帖子类截图，沉淀公开表达、互动和时间线线索。', den: 'Social posts and feeds that retain public expressions, interactions, and timeline cues.' },
      { img: 'assets/media/nodes/food.png', zh: '其他移动场景', en: 'OTHER MOBILE SCENES', dzh: '补充地图、天气、美食、风景等常见手机视觉元素。', den: 'Additional mobile visuals such as maps, weather screens, food images, and scenery.' },
    ],
    uid10: [
      { core: true, zh: '海外用户画像', en: 'GLOBAL PROFILE', dzh: '面向海外用户的文字画像核心，汇聚基础属性、社交关系与移动场景偏好。', den: 'A text-profile core for an overseas persona, combining attributes, relationships, and mobile-scene preferences.' },
      { img: 'assets/media/nodes/uid10/person.png', zh: '人物参考照', en: 'PERSON REFERENCE', dzh: '海外人物参考图，用于保持人物身份一致。', den: 'Overseas persona reference image used to keep identity consistent.' },
      { img: 'assets/media/nodes/uid10/friend.png', zh: '朋友联系人', en: 'FRIEND REFERENCES', dzh: '知识图谱中的朋友与联系人参考图。', den: 'Friend and contact references from the personal knowledge graph.' },
      { img: 'assets/media/nodes/uid10/chat.png', zh: '群聊记录', en: 'GROUP CHATS', dzh: '群聊截图记录参与者、消息和跨会话线索。', den: 'Group-chat screenshots preserving participants, messages, and cross-session cues.' },
      { img: 'assets/media/nodes/uid10/book.png', zh: '阅读记录', en: 'BOOK RECORDS', dzh: '阅读平台截图记录书名、进度与阅读兴趣。', den: 'Reading-platform screenshots with titles, progress, and interests.' },
      { img: 'assets/media/nodes/uid10/music.png', zh: '音乐记录', en: 'MUSIC RECORDS', dzh: '音乐平台记录播放内容、歌单和偏好。', den: 'Music-platform records for playback, playlists, and preferences.' },
      { img: 'assets/media/nodes/uid10/video.png', zh: '视频记录', en: 'VIDEO RECORDS', dzh: '视频平台截图承载标题、封面和互动信息。', den: 'Video-platform screenshots with titles, covers, and engagement metadata.' },
      { img: 'assets/media/nodes/uid10/money.png', zh: '交易记录', en: 'TRANSACTIONS', dzh: '账单与支付截图记录金额、商户和时间。', den: 'Payment screenshots preserving amounts, merchants, and timestamps.' },
      { img: 'assets/media/nodes/uid10/ticket.png', zh: '票务记录', en: 'TICKETS', dzh: '票务图像锚定出行、活动或预约事件。', den: 'Ticket images anchoring travel, event, or reservation memories.' },
      { img: 'assets/media/nodes/uid10/shopping.png', zh: '购物记录', en: 'SHOPPING', dzh: '购物截图记录商品、价格和购买选择。', den: 'Shopping screenshots capturing products, prices, and purchase choices.' },
      { img: 'assets/media/nodes/uid10/event.png', zh: '事件照片', en: 'EVENT PHOTOS', dzh: '事件场景照片将人物经历落到具体时间与地点。', den: 'Event photos ground the persona experience in concrete times and places.' },
      { img: 'assets/media/nodes/uid10/scenery.png', zh: '生活场景', en: 'LIFE SCENES', dzh: '风景、室内和生活图片补充移动记忆的环境上下文。', den: 'Scenery and lifestyle images add environmental context to mobile memory.' },
    ],
  };
  const memCanvas = $('#memCanvas');
  if (memCanvas) {
    const ctx = memCanvas.getContext('2d');
    const memInfo = $('#memInfo');
    const iT = $('#memInfoTitle'), iE = $('#memInfoEn'), iD = $('#memInfoDesc'), iImg = $('#memInfoImg');
    const MONO = '"Source Code Pro", monospace';
    const SANS = '"Source Sans Pro", "Microsoft YaHei", sans-serif';
    const imgCache = new Map();
    let personaId = 'uid0';
    let memNodes = memoryPersonas[personaId];
    const loadNodeImages = (nodes) => {
      nodes.filter((n) => n.img && !imgCache.has(n.img)).forEach((n) => {
        const img = new Image();
        img.onload = () => imgCache.set(n.img, img);
        img.src = n.img;
      });
    };
    const drawNodeImage = (img, sx, sy, r, { alpha = 1, stroke, lineWidth = 1.5 } = {}) => {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(img, sx - r, sy - r, r * 2, r * 2);
      ctx.restore();
      if (stroke) {
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineWidth;
        ctx.stroke();
      }
    };
    let W = 0, H = 0;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    const layoutNodes = () => {
      const sats = memNodes.filter((n) => !n.core);
      sats.forEach((n, i) => {
        const k = i + 0.5, n2 = sats.length;
        const phi = Math.acos(1 - 2 * k / n2);
        const tha = Math.PI * (1 + Math.sqrt(5)) * k;
        n.x = Math.cos(tha) * Math.sin(phi);
        n.y = Math.sin(tha) * Math.sin(phi);
        n.z = Math.cos(phi);
      });
      memNodes.filter((n) => n.core).forEach((n) => { n.x = n.y = n.z = 0; });
      loadNodeImages(memNodes);
    };
    layoutNodes();
    let rotY = 0.4, rotX = -0.25, autoRot = true, drag = false, lastX = 0, lastY = 0;
    const vel = 0.0035;
    let hover = null, selected = null, mx = -1, my = -1;
    const resize = () => {
      const r = memCanvas.getBoundingClientRect();
      W = r.width; H = r.height;
      memCanvas.width = W * DPR; memCanvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    };
    window.addEventListener('resize', resize);
    const project = (n) => {
      const cy = Math.cos(rotY), sy = Math.sin(rotY);
      const x1 = n.x * cy - n.z * sy, z1 = n.x * sy + n.z * cy;
      const cx = Math.cos(rotX), sx = Math.sin(rotX);
      const y1 = n.y * cx - z1 * sx, z2 = n.y * sx + z1 * cx;
      const R = Math.min(W, H) * 0.34, focal = 2.4, sc = focal / (focal + z2);
      return { sx: W / 2 + x1 * R * sc, sy: H / 2 + y1 * R * sc, z: z2, sc };
    };
    const labelOf = (n) => (lang === 'zh' ? n.zh : n.en);
    const rrect = (x, y, w, h, rad) => {
      ctx.beginPath();
      if (ctx.roundRect) { ctx.roundRect(x, y, w, h, rad); return; }
      ctx.moveTo(x + rad, y);
      ctx.arcTo(x + w, y, x + w, y + h, rad);
      ctx.arcTo(x + w, y + h, x, y + h, rad);
      ctx.arcTo(x, y + h, x, y, rad);
      ctx.arcTo(x, y, x + w, y, rad);
    };
    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      ctx.globalAlpha = 1;
      const pts = memNodes.map((n) => ({ n, p: project(n) }));
      const core = pts.find((o) => o.n.core);
      const R0 = Math.min(W, H) * 0.54;
      const bg = ctx.createRadialGradient(core.p.sx, core.p.sy, 0, core.p.sx, core.p.sy, R0);
      bg.addColorStop(0, 'rgba(24,160,111,0.12)');
      bg.addColorStop(0.55, 'rgba(18,128,90,0.04)');
      bg.addColorStop(1, 'rgba(18,128,90,0)');
      ctx.fillStyle = bg;
      ctx.beginPath(); ctx.arc(core.p.sx, core.p.sy, R0, 0, 7); ctx.fill();
      pts.filter((o) => !o.n.core).forEach((o) => {
        const depth = (o.p.z + 1) / 2;
        const hot = o.n === hover || o.n === selected;
        const a = hot ? 0.65 : (0.08 + 0.22 * depth);
        const grad = ctx.createLinearGradient(core.p.sx, core.p.sy, o.p.sx, o.p.sy);
        grad.addColorStop(0, `rgba(18,128,90,${a * 0.35})`);
        grad.addColorStop(1, `rgba(24,160,111,${a})`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = hot ? 1.8 : (0.5 + depth);
        ctx.beginPath(); ctx.moveTo(core.p.sx, core.p.sy); ctx.lineTo(o.p.sx, o.p.sy); ctx.stroke();
      });
      pts.sort((a, b) => a.p.z - b.p.z);
      for (const o of pts) {
        const { n, p } = o;
        const depth = (p.z + 1) / 2;
        const alpha = 0.45 + 0.55 * depth;
        const baseR = (n.core ? 17 : 11) * p.sc * (1 + 0.28 * depth);
        const isHot = n === hover || n === selected;
        const nodeImg = n.img ? imgCache.get(n.img) : null;
        if (n.core) {
          ctx.globalAlpha = 1;
          const cg = ctx.createRadialGradient(p.sx, p.sy, baseR, p.sx, p.sy, baseR + 20);
          cg.addColorStop(0, 'rgba(24,160,111,0.28)');
          cg.addColorStop(1, 'rgba(24,160,111,0)');
          ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(p.sx, p.sy, baseR + 20, 0, 7); ctx.fill();
          ctx.beginPath(); ctx.arc(p.sx, p.sy, baseR + 6, 0, 7); ctx.strokeStyle = 'rgba(18,128,90,.6)'; ctx.lineWidth = 1.6; ctx.stroke();
          ctx.beginPath(); ctx.arc(p.sx, p.sy, baseR, 0, 7); ctx.fillStyle = '#f8fafc'; ctx.fill();
          ctx.strokeStyle = '#12805a'; ctx.lineWidth = 2; ctx.stroke();
          ctx.fillStyle = '#12805a'; ctx.font = '700 7px ' + (lang === 'zh' ? SANS : MONO); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(lang === 'zh' ? '画像' : 'PROFILE', p.sx, p.sy - 3);
          ctx.fillStyle = 'rgba(18,128,90,0.28)';
          ctx.fillRect(p.sx - baseR * 0.42, p.sy + 4, baseR * 0.84, 1.4);
          ctx.fillRect(p.sx - baseR * 0.34, p.sy + 8, baseR * 0.68, 1.4);
          continue;
        }
        const r = isHot ? baseR * 1.3 : baseR;
        ctx.globalAlpha = 1;
        if (isHot) {
          const hg = ctx.createRadialGradient(p.sx, p.sy, r * 0.5, p.sx, p.sy, r * 2.4);
          hg.addColorStop(0, 'rgba(24,160,111,0.4)');
          hg.addColorStop(1, 'rgba(24,160,111,0)');
          ctx.fillStyle = hg; ctx.beginPath(); ctx.arc(p.sx, p.sy, r * 2.4, 0, 7); ctx.fill();
        }
        if (nodeImg) {
          drawNodeImage(nodeImg, p.sx, p.sy, r, {
            alpha,
            stroke: isHot ? '#18a06f' : `rgba(18,128,90,${0.2 + 0.4 * depth})`,
            lineWidth: isHot ? 2.4 : 1.2,
          });
        } else {
          ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, 7); ctx.fillStyle = isHot ? '#18a06f' : `rgba(17,17,17,${alpha})`; ctx.fill();
        }
        if (depth > 0.55 || isHot) {
          const label = labelOf(n);
          ctx.font = `${isHot ? '700' : '500'} ${11 * Math.max(p.sc, 0.7)}px ${SANS}`;
          ctx.textAlign = 'center'; ctx.textBaseline = 'top';
          const ly = p.sy + r + 5;
          if (isHot) {
            const tw = ctx.measureText(label).width;
            rrect(p.sx - tw / 2 - 7, ly - 3, tw + 14, 18, 9);
            ctx.fillStyle = '#12805a'; ctx.fill();
            ctx.fillStyle = '#fff'; ctx.fillText(label, p.sx, ly);
          } else {
            ctx.fillStyle = `rgba(17,17,17,${0.5 + 0.5 * depth})`;
            ctx.fillText(label, p.sx, ly);
          }
        }
      }
    };
    const tick = () => {
      if (autoRot && !drag) rotY += vel;
      hover = null;
      if (mx >= 0) {
        let best = null, bd = 18;
        for (const n of memNodes) {
          const p = project(n);
          const d = Math.hypot(p.sx - mx, p.sy - my);
          const rr = (n.core ? 17 : 11) * p.sc + 10;
          if (d < rr && d < bd) { bd = d; best = n; }
        }
        hover = best;
        memCanvas.style.cursor = best ? 'pointer' : (drag ? 'grabbing' : 'grab');
      }
      draw();
      requestAnimationFrame(tick);
    };
    const showMemInfo = (n) => {
      if (!memInfo) return;
      if (iImg) {
        if (n.img) { iImg.src = n.img; iImg.removeAttribute('hidden'); memInfo.classList.remove('is-text'); }
        else { iImg.setAttribute('hidden', ''); memInfo.classList.add('is-text'); }
      }
      iT.textContent = labelOf(n); iE.textContent = n.en; iD.textContent = lang === 'zh' ? n.dzh : n.den;
      memInfo.classList.add('is-on');
    };
    const switchPersona = (nextId) => {
      if (!memoryPersonas[nextId] || nextId === personaId) return;
      personaId = nextId;
      memNodes = memoryPersonas[personaId];
      selected = null; hover = null; mx = -1; my = -1;
      memInfo?.classList.remove('is-on', 'is-text');
      layoutNodes();
      $$('.mem-persona-tab').forEach((btn) => {
        const isActive = btn.dataset.memPersona === personaId;
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-pressed', String(isActive));
      });
    };
    memCanvas.addEventListener('pointerdown', (e) => { drag = true; lastX = e.offsetX; lastY = e.offsetY; memCanvas.setPointerCapture(e.pointerId); });
    memCanvas.addEventListener('pointermove', (e) => {
      mx = e.offsetX; my = e.offsetY;
      if (drag) { rotY += (e.offsetX - lastX) * 0.006; rotX += (e.offsetY - lastY) * 0.006; rotX = Math.max(-1.2, Math.min(1.2, rotX)); lastX = e.offsetX; lastY = e.offsetY; }
    });
    memCanvas.addEventListener('pointerup', () => { drag = false; if (hover) { selected = hover; showMemInfo(hover); } });
    memCanvas.addEventListener('pointerleave', () => { mx = -1; my = -1; drag = false; });
    window.__memRefresh = () => { if (selected) showMemInfo(selected); };
    $$('.mem-persona-tab').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.classList.contains('is-active')));
      btn.addEventListener('click', () => switchPersona(btn.dataset.memPersona));
    });
    resize(); tick();
  }

  applyLang(lang);
})();
