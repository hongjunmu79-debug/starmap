/* 星图的数据（从 2D 版原样抽出）。constellations：4 个星座中心（id、title、domain 领域、status 状态、icon、includes 成员文字、incIcons 成员图标，
   at 是 2D 版的坐标，3D 版不用）；domains：6 个领域和颜色，unsortedColor 是还没归类的想法的颜色；ideas：想法；links：已有的提议线；
   hints：拖近时才浮出的线索；expansions：双击或新想法后长出的可能性示例（key 是节点 id）；icons：19 个 24x24 线条图标的 SVG path；
   lensIcons：可能性种类对应的图标。 */
const DATA = {
  domains: [
    { id: 'self',     name: '个人系统',   color: '#9B7BFF' },
    { id: 'ai',       name: 'AI 与技术',  color: '#4DA3FF' },
    { id: 'edu',      name: '教育',       color: '#2FD3A0' },
    { id: 'industry', name: '行业与职业', color: '#FFB020' },
    { id: 'social',   name: '游戏与社交', color: '#FF6F91' },
    { id: 'create',   name: '创作与产品', color: '#F5E663' }
  ],
  unsortedColor: '#E8E4DA',
  legendNote: '亮：在跑　暗：冻结　白：还没归类',
  icons: {
    chip:     'M8 7h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z M10 10h4v4h-4z M10 4v3 M14 4v3 M10 17v3 M14 17v3 M4 10h3 M4 14h3 M17 10h3 M17 14h3',
    gear:     'M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z M12 6a6 6 0 1 0 0 12a6 6 0 1 0 0-12z M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6L7.8 7.8 M16.2 16.2L18.4 18.4 M5.6 18.4L7.8 16.2 M16.2 7.8L18.4 5.6',
    check:    'M5 5h14v14H5z M8.5 12.5l2.5 2.5l4.5-5',
    chat:     'M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 4v-4H6a2 2 0 0 1-2-2z',
    spark:    'M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z',
    people:   'M9 11a3 3 0 1 0 0-6a3 3 0 1 0 0 6z M3 20a6 6 0 0 1 12 0 M16 11a2.5 2.5 0 1 0 0-5 M17 14.5a5 5 0 0 1 4 5.5',
    dice:     'M5 5h14v14H5z M9 9h.01 M12 12h.01 M15 15h.01',
    card:     'M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z M12 9l2.5 3l-2.5 3l-2.5-3z',
    cap:      'M2 9l10-5l10 5l-10 5z M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5 M22 9v5',
    flask:    'M9 3h6 M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3 M7.5 15h9',
    doc:      'M6 3h8l4 4v14H6z M14 3v4h4 M9 12h6 M9 16h6',
    book:     'M3 5h6a3 3 0 0 1 3 3v12a2.5 2.5 0 0 0-2.5-2.5H3z M21 5h-6a3 3 0 0 0-3 3v12a2.5 2.5 0 0 1 2.5-2.5H21z',
    tool:     'M14.5 3.5a4.5 4.5 0 0 0-4.2 6.1L3.5 16.4a1.5 1.5 0 0 0 2.1 2.1l6.8-6.8a4.5 4.5 0 0 0 6.1-4.2l-2.6 2.6l-2.1-.5l-.5-2.1z',
    sliders:  'M4 7h16 M4 12h16 M4 17h16 M9 5v4 M15 10v4 M7 15v4',
    db:       'M5 6a7 2.5 0 1 0 14 0a7 2.5 0 1 0-14 0z M5 6v12a7 2.5 0 0 0 14 0V6 M5 12a7 2.5 0 0 0 14 0',
    bulb:     'M9 18h6 M10 21h4 M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z',
    flag:     'M5 21V4 M5 4h11l-2 4l2 4H5',
    question: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14 M12 17h.01',
    link:     'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'
  },
  lensIcons: { '可以变成': 'spark', '第一步': 'flag', '卡在': 'question', '像': 'link', '连着': 'link', '两者之间': 'spark' },
  constellations: [
    { id: 'personal-os', domain: 'self', status: 'explore', icon: 'gear', incIcons: ['check', 'chat', 'spark', 'chip', 'chip', 'check'], title: '个人工作台', at: [-430, -230], includes: [
      '待办工作台（已完成，想扩展）', '想法记录系统（飞书、Telegram、微信发给 Hermes）', '灵感速记（星空思维导图）',
      '思维收集器硬件', 'ESP32「坐下即知」', '实体指挥台的「今日任务」'] },
    { id: 'offline-social', domain: 'social', status: 'pool', icon: 'people', incIcons: ['dice', 'people', 'card'], title: '线下陌生人局', at: [430, -210], includes: [
      '线下互动娱乐交友 station', '新身份认同社交中心', '实体指挥台的狼人杀、阿瓦隆（20 张 NFC 卡）'] },
    { id: 'school', domain: 'edu', status: 'running', icon: 'cap', incIcons: ['flask', 'doc', 'book'], title: '中东学校', at: [-380, 260], includes: [
      'ESP32 三语科学实验台', '一键备课', '老师工作台'] },
    { id: 'land-lease', domain: 'industry', status: 'running', icon: 'doc', incIcons: ['doc', 'book', 'tool', 'sliders', 'db', 'bulb'], title: '土地租赁合同重做', at: [420, 270], includes: [
      '土地租赁合同管理重做', '产品方法论（AI-native SDLC）', '黑客松工作台', '小模型微调', 'LLM wiki 与企业知识库', '产品经理默会知识'] }
  ],
  ideas: [
    { id: 'boardgame', text: '做一个桌游', icon: 'dice', at: [250, -40] }
  ],
  hints: [
    { a: 'inc:school:1',         b: 'inc:land-lease:5',     kind: 'supports',    label: '备课经验算默会知识吗？' },
    { a: 'inc:school:2',         b: 'inc:personal-os:0',    kind: 'same',        label: '能共用一个工作台吗？' },
    { a: 'inc:school:0',         b: 'inc:personal-os:4',    kind: 'same',        label: '同一块 ESP32？' },
    { a: 'inc:land-lease:4',     b: 'inc:personal-os:1',    kind: 'extends',     label: '想法能进知识库吗？' },
    { a: 'inc:land-lease:3',     b: 'inc:personal-os:2',    kind: 'extends',     label: '用你的想法微调？' },
    { a: 'inc:land-lease:2',     b: 'inc:offline-social:0', kind: 'extends',     label: '办一场线下黑客松？' },
    { a: 'inc:offline-social:2', b: 'inc:school:0',         kind: 'extends',     label: 'NFC 卡能进课堂吗？' },
    { a: 'idea:boardgame',       b: 'inc:offline-social:2', kind: 'part_of',     label: '桌游就用这 20 张卡？' },
    { a: 'inc:land-lease:1',     b: 'inc:personal-os:2',    kind: 'contradicts', label: '流程会掐死灵感吗？' },
    { a: 'inc:personal-os:5',    b: 'inc:offline-social:2', kind: 'same',        label: '同一个指挥台？' }
  ],
  links: [
    { a: 'inc:personal-os:3', b: 'inc:offline-social:2', kind: 'confirmed', label: '同一块硬件' },
    { a: 'idea:boardgame', b: 'item:offline-social', kind: 'suggest', label: '属于这件事吗？' },
    { a: 'idea:boardgame', b: 'inc:school:0', kind: 'suggest', label: '能变成课堂游戏吗？' },
    { a: 'inc:personal-os:2', b: 'inc:land-lease:5', kind: 'suggest', label: '能装下默会知识吗？' }
  ],
  expansions: {
    'idea:boardgame': [
      { id: 'bg1', lens: '可以变成', text: '拿 20 张 NFC 卡当牌，刷卡出题' },
      { id: 'bg2', lens: '可以变成', text: '中东学校的三语实验桌游' },
      { id: 'bg3', lens: '第一步', text: '一页纸：几人玩、一局多久、每回合做什么决定' },
      { id: 'bg4', lens: '卡在', text: '每回合到底让人纠结什么？' },
      { id: 'bg5', lens: '像', text: '狼人杀：靠说服别人赢' }
    ],
    'poss:bg1': [
      { id: 'bg1a', lens: '第一步', text: '先用纸卡试玩一局，不碰硬件' },
      { id: 'bg1b', lens: '卡在', text: 'AI 出题会不会拖慢节奏？' },
      { id: 'bg1c', lens: '可以变成', text: '实体指挥台当裁判，屏幕计分' }
    ],
    'poss:bg4': [
      { id: 'bg4a', lens: '可以变成', text: '押注：猜别人会怎么选' },
      { id: 'bg4b', lens: '像', text: '阿瓦隆的组队投票' }
    ],
    'idea:phone-demo': [
      { id: 'ph1', lens: '连着', text: '产品经理默会知识' },
      { id: 'ph2', lens: '可以变成', text: '一键备课时顺手记下老师的「为什么」' },
      { id: 'ph3', lens: '第一步', text: '问一位老师：哪个决定她不假思索就做了？' },
      { id: 'ph4', lens: '卡在', text: '默会的东西，老师自己说得出来吗？' }
    ]
  },
  sparks: {
    'inc:offline-social:2|inc:personal-os:3': '把想法卡做成 NFC 卡：刷一张，收一个念头'
  },
  phoneDemo: { id: 'phone-demo', text: '老师备课的经验，算不算默会知识？', icon: 'bulb', tag: '手机 · 记个想法（示例）', at: [20, 300] },
  placeholder: [
    { lens: '可以变成', text: '（原型示例）它可以变成…' },
    { lens: '第一步', text: '（原型示例）30 分钟能做的第一步…' },
    { lens: '卡在', text: '（原型示例）最没把握的地方…' }
  ],
  sparkPlaceholder: '（原型示例）这两条之间，会长出什么？',
  sparkLens: '两者之间',
  hint: '拖近：有关系会浮出线索 · 快速一划：切断线（Ctrl+Z 撤销）· 拉线中间：弹弓 · 单击：聚焦 · 双击：长出可能性 · 左下角：连线 / 批注 / 刷子 · Esc：退回',
  badge: '原型 · 可能性文字是示例'
};
