# Hotline 统一 UI 基础层

本目录是前端样式的唯一新增入口。`ui.css` 定义全站共用的面板、表格、状态、空态与列表类；
页面不再各自实现表格与空态。新增页面或新表格一律从这里取类，不要再写第二套。

规则与背景见 `docs/spec/2026-11-24-统一UI基础层与表格体系.md`（S-019），视觉令牌见 `DESIGN.md`。

## 面板

- `.harness-panel`：带描边与圆角的内容面板，承载一组相关数据。
- `.harness-panel-heading`：面板标题行，标题用 `h3`，右侧可放 `.harness-panel-actions`。
- 页面只允许一个 `h1`；面板标题从 `h3` 起。

```html
<section class="harness-panel">
  <div class="harness-panel-heading">
    <div>
      <h3>Agent 目录</h3>
      <p>12 个 Agent · 已连接资源目录</p>
    </div>
    <div class="harness-panel-actions">
      <button class="button button-subtle">刷新目录</button>
      <button class="button button-primary">新建 Agent</button>
    </div>
  </div>
  ...
</section>
```

## 表格

结构固定三层：容器 `.ui-table` → 表头 `.ui-table-head` → 行 `.ui-row`。

- 列宽由**语义列类**决定，挂在 `.ui-table` 容器上，表头与行共用同一组列数，不会错位。
- 列类的列数必须等于表头单元格数，也等于每个行子元素数。新增表格先选列类，没有合适的就新增一个列类。
- 行内主次信息用 `<strong>` / `<small>` 表达，不另起标签。
- 语义化真 `<table>` 加 `.ui-table-real` 基类，与 div 表格同一套表头、行高与 hover。

```html
<div class="ui-table ui-cols-workspace">
  <div class="ui-table-head">
    <span>名称</span><span>仓库</span><span>分支</span><span>状态</span><span>操作</span>
  </div>
  <div class="ui-row">
    <span><strong>demo</strong><small>ws-001</small></span>
    <span>repo</span><span>main</span><span>就绪</span>
    <button class="text-action">查看</button>
  </div>
</div>
```

### 列类一览

| 列类 | 列数 | 用途 |
| --- | --- | --- |
| `.ui-cols-generic` | 5 | 通用目录表（名称 / 版本 / 模型 / 状态 / 操作） |
| `.ui-cols-workspace` | 5 | 工作空间、审批通知 |
| `.ui-cols-machine` | 7 | 运行时节点 |
| `.ui-cols-machine-summary` | 6 | 概览页节点摘要 |
| `.ui-cols-approval` | 6 | 审批队列 |
| `.ui-cols-trace` | 5 | 运行 Trace |
| `.ui-cols-trace-event` | 5 | 运行事件 |
| `.ui-cols-trend` | 7 | 指标趋势 |
| `.ui-cols-mcp` | 4 | MCP 连接器 |
| `.ui-cols-dataset` | 6 | 测评集 |
| `.ui-cols-rollout` | 6 | 灰度推进 |
| `.ui-cols-release-record` | 9 | 发布记录 |
| `.ui-cols-history` | 5 | 无表头记录行（灰度观察、门禁记录、快照） |
| `.ui-cols-report` | 4 | 历史报告 |
| `.ui-cols-error-log` | 3 | 节点错误日志 |
| `.ui-cols-eval-results` | 10 | Agent 测评结果明细 |

无表头的记录行用 `.ui-cols-history` 一类，行子元素数仍须等于列数。

## 状态标记

统一 `.ui-status`，四档语义，圆点加文字，颜色之外还有文字，不靠颜色单独传达信息。

| 档位 | 含义 |
| --- | --- |
| `ok` | 成功、在线、已连接、已启用 |
| `warn` | 等待、进行中、需关注 |
| `err` | 失败、未通过 |
| `idle` | 未记录、停用、未连接 |

```html
<span class="ui-status" :class="row.enabled === true ? 'ok' : 'idle'">{{ row.enabled ? '启用' : '停用' }}</span>
```

旧的 `dataset-state`、`plugin-state`、`health-mini`、`machine-led` 已全部删除，不要再用。

## 空态

统一 `.ui-empty`：可选图标（`.ui-empty-icon`）+ `h3` 标题 + 一句说明 + 可选主按钮。
侧栏或行内的小提示用 `.ui-empty-inline`。

```html
<div class="ui-empty">
  <div class="ui-empty-icon"><Puzzle :size="26" /></div>
  <h3>还没有安装技能</h3>
  <p>上传技能包后，机器人就能绑定它并按它的方式干活。</p>
  <button class="primary-button" type="button">上传技能包</button>
</div>
```

页面已有 `h1`，空态标题用 `h3`。

## 列表

卡片式列表（非表格）用 `.ui-list`：容器 `.ui-list` → 行 `.ui-list-row` → 主区 `.ui-list-main` + 操作区 `.ui-list-actions`。
主区内部用 `.ui-list-title` / `.ui-list-desc` / `.ui-list-meta` 三级文本。

```html
<div class="ui-list">
  <div class="ui-list-row">
    <div class="ui-list-main">
      <p class="ui-list-title"><strong>memory-bank</strong><span class="ui-status ok">已启用</span></p>
      <p class="ui-list-desc">长期项目记忆</p>
      <p class="ui-list-meta">来源 skills/memory-bank · 入口 SKILL.md</p>
    </div>
    <div class="ui-list-actions">
      <button class="text-action">停用</button>
      <button class="text-action danger">删除</button>
    </div>
  </div>
</div>
```

## 按钮

只允许四种主操作写法，不新增第五种：

| 类 | 用途 |
| --- | --- |
| `primary-button` | 页面主操作（黑底白字） |
| `secondary-button` | 次要操作（描边） |
| `button button-subtle` / `button button-primary` | Harness 面板内按钮 |
| `text-action` / `text-action danger` | 行内文字操作，`danger` 为破坏性 |

同一页面的主操作只出现一次：侧栏按钮与内容区工具条按钮二选一，空态 CTA 保留。

## 不纳入本层

聊天页的消息流与输入区密度与工作台页面不同，另立规格评估；`static/console/console.css`
是静态技能控制台，不在 Vue 应用内，不与本层合并。
