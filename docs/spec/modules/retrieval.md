# 检索与向量召回（retrieval）

> 模块路径：`python_backend/modules/retrieval/` ｜ 前端对应：`frontend/src/modules/retrieval/`（只有 `.gitkeep` 占位，无前端模块）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## pgvector 适配与文档分段写入

### 入口

- `python_backend/modules/retrieval/vector_store.py:PgVectorStore` —— pgvector 适配器，文档与工作区两条召回链路共用
- `vector_store.py:PgVectorStore.index_document` —— 父块不向量化、子块向量化后写入
- `vector_store.py:PgVectorStore.search_expanded_files` —— 跨多文件召回并回填父块整节内容
- `python_backend/modules/documents/service.py:DocumentService.vectorize` —— 文档向量化总入口

### 行为

- 构造时不连接，仅在开启向量库时惰性建连；建连失败不抛异常，原因记进 `error`，并在 30 秒内不再重试。
- `ready()` 先校验 embedding key，缺失时 `error` 指向配置项名，再触发一次连接尝试。
- 首次连接自动建表建索引：`CREATE EXTENSION IF NOT EXISTS vector`、分块表、父子块表、关系表、分块表的 HNSW 余弦索引；表名只允许字母数字与下划线，否则抛 `ValueError`。
- 向量化走 OpenAI 兼容的 `/embeddings` 接口，超时 90 秒，发送前经 `context_engineering.privacy.sanitize_text` 脱敏；`embed_batch` 一次请求多条文本并按返回的 `index` 排序对应。
- 父块按 `id` upsert 存整节正文并标记 `skip_embedding=true`；子块逐条写入，携带 `fileid`、`chunkId`、`parentChunkId`、`heading`。
- 检索按余弦距离 `<=>` 排序取 top_k（默认 5）条子块，命中后回查父块：父块存在就用整节正文替换片段；多文件召回只算一次 query 向量，文件集合用 `ANY` 一次过滤。
- 文档向量化前先按文档 ID 清理旧行，重试不留半截数据，写完后状态置 `VECTORIZED`。

### 关键实现

- `vector_store.py:PgVectorStore._connect` / `_initialise` / `document_chunks` —— 建连建表、按 chunkId 数值排序取回文档分段
- 配置项：`DODO_VECTOR_ENABLED`、`DODO_VECTOR_HOST`、`DODO_VECTOR_PORT`、`DODO_VECTOR_DATABASE`、`DODO_VECTOR_USER`、`DODO_VECTOR_PASSWORD`、`DODO_VECTOR_TABLE`、`DODO_VECTOR_PARENT_TABLE`、`DODO_VECTOR_DIMENSION`、`DODO_EMBEDDING_API_KEY`、`DODO_EMBEDDING_BASE_URL`、`DODO_EMBEDDING_MODEL`

## 关键词、图谱与受限 Text2SQL 召回

### 入口

- `vector_store.py:PgVectorStore.search_keyword` —— 分块正文子串匹配
- `vector_store.py:PgVectorStore.search_graph` —— 关系表三元组匹配
- `vector_store.py:PgVectorStore.search_text2sql` —— 校验并执行模型生成的只读 SQL
- `python_backend/modules/execution/engine.py:AgentEngine._retrieve` —— 按检索路由分发到语义/关键词/图谱/Text2SQL

### 行为

- 关键词召回抽词规则：英数下划线串或连续中文段，长度不少于 2，去重后取前 8 个；命中判断是 `ILIKE` 子串包含，不依赖分词器，中文可直接命中，命中同样回填父块正文并按归一化正文去重。
- 图谱召回对关系表的 `subject`、`predicate`、`object` 三列做同样的子串匹配，结果格式固定为「图谱关系：主语 -[谓词]-> 宾语」加一行来源证据；关系写入先按文档 ID 清空旧关系，只写主谓宾与证据都非空的三元组。
- Text2SQL 只接受一种固定形状：`SELECT content FROM <分块表> WHERE metadata->>'fileid' = :file_id`，可选追加 `AND content ILIKE '...'` 与 `LIMIT n`；形状不匹配直接抛 `ValueError`，模型生成的 SQL 不会被原样执行。
- Text2SQL 行数上限取「模型请求值、`top_k`（默认 8）、20」三者最小，ILIKE 条件里的 `%`、`_` 会转义，不会变成通配符。

### 关键实现

- `vector_store.py:PgVectorStore._terms` / `replace_graph` —— 抽词规则与关系表整体替换
- `python_backend/modules/execution/engine.py:AgentEngine._text2sql` —— 让模型生成 SQL 后调用 `search_text2sql`

## 工作区文件索引与分层词面召回

### 入口

- `python_backend/modules/retrieval/workspace_index.py:WorkspaceIndex.index_directory` —— 扫描工作区目录并建词面索引
- `workspace_index.py:WorkspaceIndex.search_sources` —— 分层词面召回，保留来源 ID
- `workspace_index.py:WorkspaceIndex.search` —— 同上，但拼成「来源 + 正文」字符串

### 行为

- 目录遍历用 `scandir`，跳过软链接、跳过跳过名单目录、跳过私密路径、跳过空文件与超过 256KB 的文件；二进制文件按前 4KB 是否含空字节判断后整份跳过；正文按行切块，每块不超过 1500 字符。
- 词面召回分四层，各自排序后交错合并：精确词层（长度不小于 3 的英文/数字标识符与错误码，走 trigram 索引）；中文三字层（中文连续段不小于 3 字时切滑窗三元组，走 trigram 索引）；中文双字层（恰好两个汉字走 bigram 表，trigram 索引不了更短的词）；兜底层（单个汉字与两字母短词走 `LIKE`，按出现次数降序、内容长度升序）。
- 每层候选上限 50，兜底层单项上限 20，每类词最多取 12 个。
- 合并时逐层轮流取一条，避免某一层把其它层挤掉，结果按归一化正文去重；召回可排除指定来源（`exclude_source`）。

### 关键实现

- `workspace_index.py:WorkspaceIndex._terms` / `_match` / `_bigram_match` / `_like` / `_merge` —— 四层分词、匹配与交错合并
- `workspace_index.py:workspace_files` —— 目录遍历与跳过规则

## 文件向量与工作区语义召回

### 入口

- `workspace_index.py:WorkspaceIndex.embed_directory` —— 给每个变更文件生成一个向量
- `workspace_index.py:WorkspaceIndex.search_files_by_vector` —— 余弦相似度排序
- `python_backend/modules/workspaces/context.py:semantic_workspace` —— 工作区语义召回装配

### 行为

- 每个工作区文件只保存一个向量，采样取文件头、中、尾三段，最长 1200 字符；向量以 float32 归一化后存进本地 SQLite 的 BLOB。
- 召回按余弦相似度排序，默认取 3 个文件，默认相似度阈值 0.35；维度不一致的向量直接跳过。
- 语义通道的候选范围由工作区成员关系决定（该工作区用过的文档与文件），不由这次问句的词面命中决定，因此无共同字面的同义问法也能召回。
- 文档侧语义证据来自 `search_expanded_files`（该工作区所有文档一次向量检索）；文件侧证据来自本地文件向量检索，每个命中文件最多给 6000 字符。
- 两条通道任一失败都不抛错，只影响该通道的证据量。

### 关键实现

- `workspace_index.py:WorkspaceIndex.store_file_vector` / `_profile` / `_normalize` —— 向量存储、文件采样与归一化

## 倒数排名融合（RRF）

### 入口

- `python_backend/modules/retrieval/fusion.py:fuse_evidence` —— 多路排序列表融合成一份证据
- `python_backend/modules/execution/engine.py:AgentEngine._merge_hits` —— 把工作区证据并入文档证据

### 行为

- 每路排序内先按归一化正文去重，排名第 r 的命中得分累加 `1/(60+r)`。
- 得分相同时按「正文里命中了几个问句词条」做次级排序，词条按英数串或连续中文段抽取。
- 输出默认最多 8 条，调用方可放大 limit 把文档证据与工作区证据一起保留；两路都命中的正文只留一份，两路各自命中的都留下。

### 关键实现

- `fusion.py:fuse_evidence` —— RRF 打分与词条 tie-break

## 来源分层、工作区隔离与增量同步

### 入口

- `workspace_index.py:WorkspaceIndex.index_source` —— 写入一个来源的分块与分层摘要
- `workspace_index.py:WorkspaceIndex.read_source` —— 按层读取来源内容
- `workspace_index.py:WorkspaceIndex.overview` —— 工作区目录覆盖清单
- `python_backend/modules/workspaces/context.py:recall_workspace` —— 同步目录、绑定文档、词面与语义召回的总装配

### 行为

- 来源标识有两种：工作区文件用 `file:<相对路径>`，绑定的文档用 `doc:<文档 ID>`。
- 每个来源存三层：`abstract`（正文首段前 256 字）、`overview`（抽取式概览 JSON）、`detail`（按原顺序拼回的全部分块）；概览 JSON 含来源 ID、`method: extractive`、总段数与最多 16 个采样段（每段前 180 字）。
- 工作区清单按目录分组（文件取路径前两段，文档归入 `documents`），每组最多带 4 条摘要，目录清单最多 64 项。
- 读取参数严格校验：偏移不小于 0，单次条数 1 到 12000 之间，层级只允许 abstract/overview/detail。
- 所有表都带 `workspace_id` 并强制按工作区过滤，不同工作区之间不互相可见；命中私密路径的来源被拒收并从索引移除。
- 文件索引用「修改时间:大小」当标记，内容没变不重读，被删掉的文件在下次同步时清除；文档来源用版本号当标记（文档用版本号，上传文件用固定值），版本没变不重复读取。

### 关键实现

- `python_backend/modules/retrieval/layers.py:source_layers` / `GLOBAL_QUERY` —— 摘要与概览生成、全局型问法识别
- `python_backend/modules/workspaces/context.py:bind_document` —— 把本轮用到的文档挂进工作区索引

## 数据与存储

- pgvector（PostgreSQL）：分块表（`DODO_VECTOR_TABLE`）、父子块表（`DODO_VECTOR_PARENT_TABLE`）、关系表 `dodo_knowledge_relation`。
- 本地 SQLite：`data/workspace-index.db`，含 `workspace_source`、`workspace_chunk_fts`（FTS5 trigram）、`workspace_chunk_bi`（FTS5 unicode61 bigram）、`workspace_file_vec` 四张表。
- 本模块不写自己的运行数据，也维护独立配置文件。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/file/upload` | 大文件切块后写入向量库（`PgVectorStore.add_chunks`） |
| `POST` | `/document/{doc_id}/vectorize` | 文档分段向量化并写入关系图谱（`DocumentService.vectorize`） |
| `GET` | `/agent/chat/stream` | 对话中触发文档检索与工作区召回（`AgentEngine._grounding`） |
| `—` | `python_backend/modules/workspaces/context.py:recall_workspace` | 工作区级召回总入口（词面 + 语义） |
| `—` | `python_backend/modules/execution/engine.py:AgentEngine._retrieve` | 按检索路由分发四条召回通道 |
| `—` | `python_backend/modules/retrieval/fusion.py:fuse_evidence` | 多路证据 RRF 融合 |

## 边界与已知限制

- 本模块没有独立 HTTP 路由，只由执行引擎、文档服务与工作区装配调用。
- pgvector 不可用时向量通道整体失效：关键词层与工作区词面层仍可用，语义层返回空。
- 文件向量是「一文件一向量」，长文件只取头中尾采样，不代表全文语义。
- 词面层只在单个工作区内检索，跨工作区不可见。
- 单字中文与两字母短词走 `LIKE`，精度低于 trigram/bigram 两层，但排序在其后。
- `PgVectorStore.add_chunks` 只追加不清理，同一 `file_id` 重复写入会留下多份分块。
- Text2SQL 只接受一种固定 SQL 形状，其余一律 `ValueError`。
- 语义召回评测需要真实 embedding 服务，默认跳过，需设 `HOTLINE_SEMANTIC_EVAL=1` 才运行。
- 词面召回质量由 `python_backend/modules/retrieval/test_recall_quality.py` 的标注集衡量，门槛为召回率不低于 0.95。
