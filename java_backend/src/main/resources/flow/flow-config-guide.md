# 流程配置说明

本目录的两个文件共同决定一个流程场景执行哪些任务、按什么顺序执行：

| 文件 | 作用 |
| --- | --- |
| `flows.json` | 按场景声明任务：每个任务的执行顺序、对应的处理器键和任务参数 |
| `flow_funcmaps.properties` | 把处理器键（`fmap`）映射到处理器的全限定类名 |

两个文件都在服务启动时加载，修改后需要重启 Java 服务。配置有误时启动会失败，并在日志中指出出错的场景和任务。

## flows.json 的结构

```json
{
  "<场景名>": {
    "<任务名>": {
      "order": "0",
      "fmap": "flow_1",
      "toggle": "1",
      "<自定义参数>": "<值>"
    }
  }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 场景名 | 是 | 代码通过它触发流程：`flowEngine.execute("<场景名>", context)` |
| 任务名 | 是 | 场景内唯一，只用于日志和报错定位 |
| `order` | 是 | 整数，写成 `"0"` 或 `0` 都可以，决定执行顺序 |
| `fmap` | 是 | 处理器键，必须在 `flow_funcmaps.properties` 中存在 |
| `toggle` | 否 | `"0"` 表示跳过该任务，不写或其他值表示执行 |
| 其他字段 | 否 | 原样作为任务参数传给处理器 |

### order 如何决定串行与并行

- 任务按 `order` 从小到大执行；`order` 相同的任务保持书写顺序。
- **`order` 相同的多个任务并行执行**，在流程线程池（线程名 `hotline-flow-N`）中运行，全部结束后才进入下一个 `order`。
- **某个 `order` 只有一个任务时串行执行**，直接在调用线程中运行。
- 任一任务抛出异常，后面的 `order` 不再执行。并行组会等组内任务全部结束，再抛出书写顺序最靠前的那个异常。

以内置的 `execution-submit` 场景为例：

```json
"execution-submit": {
  "validate-submission": { "order": "0", "fmap": "flow_1", "maxQueryLength": "20000" },
  "submission-quota":    { "order": "0", "fmap": "flow_2" },
  "create-run":          { "order": "1", "fmap": "flow_3" },
  "submission-ledger":   { "order": "2", "fmap": "flow_4", "toggle": "1" }
}
```

执行过程是：参数校验与配额检查并行 → 创建运行 → 记账。

### 任务参数

除 `order`、`fmap` 以外的字段都会进入处理器收到的 `params`，另外自动带上 `_scene`（场景名）和 `_task`（任务名）。字符串、布尔和数字保留原类型；嵌套对象和数组以 Jackson `JsonNode` 传入。

继承 `AbstractFlowProcessor` 的处理器可以用 `stringParam`、`intParam`、`booleanParam` 读取参数并提供默认值，例如：

```java
int maxQueryLength = intParam(params, "maxQueryLength", 20_000);
```

## flow_funcmaps.properties 的写法

```properties
flow_9=cn.hotline.application.flow.task.MyNewProcessor
```

- 键约定为 `flow_<序号>`，新增时接着现有最大序号往下编。
- 值是处理器的全限定类名，类必须实现 `FlowItemProcessor`。
- 同一个键可以被多个场景、多个任务引用。
- 键不要重复：重复时后一行会悄悄覆盖前一行。
- 文件只写 ASCII 字符。`.properties` 按 ISO-8859-1 读取，中文注释在多数编辑器里会显示成乱码。

## 新增一个任务的步骤

1. **编写处理器**。放在 `cn.hotline.application.flow.task` 包下，继承 `AbstractFlowProcessor`：

   ```java
   @Component
   public class MyNewProcessor extends AbstractFlowProcessor {

       @Override
       protected void doProcess(FlowContext context, Map<String, Object> params) {
           String input = context.require(FlowKeys.SUBMISSION, ExecutionSubmission.class).query();
           context.put("my-result", input.length());
       }
   }
   ```

   - 加 `@Component` 后可以通过构造器注入其他 Bean；不加时必须有无参构造器，由反射创建。
   - 每个处理器只有一个实例，会被多个请求和线程同时调用，不要在成员变量里保存请求数据。
   - 任务之间只通过 `FlowContext` 交换数据：`context.put(key, value)` 写入，`context.require(key, 类型)` 读取（缺失时抛异常）。公用的键定义在 `FlowKeys` 中。

2. **登记映射**。在 `flow_funcmaps.properties` 追加一行：

   ```properties
   flow_9=cn.hotline.application.flow.task.MyNewProcessor
   ```

3. **加入场景**。在 `flows.json` 对应场景下添加任务，并选好 `order`：

   ```json
   "my-new-task": { "order": "1", "fmap": "flow_9", "threshold": "10" }
   ```

   并行任务之间没有先后保证。如果新任务要读取另一个任务写入上下文的数据，它的 `order` 必须比那个任务大。

4. **重启服务**。启动日志会输出每个场景加载到的任务数。

## 新增一个场景的步骤

1. 在 `flows.json` 顶层增加一个场景名，并按上面的方式写入任务。
2. 在 `FlowKeys` 中为场景名和上下文键增加常量。
3. 在应用服务中触发流程并取回结果：

   ```java
   FlowContext context = new FlowContext("my-scene");
   context.put("my-input", input);
   flowEngine.execute("my-scene", context);
   return context.require("my-result", MyResult.class);
   ```

   可参考 `CapabilityOverviewService` 和 `ExecutionSubmissionService`。

## 临时关闭一个任务

把任务的 `toggle` 设为 `"0"` 后重启即可，无需删除配置。只有继承 `AbstractFlowProcessor` 的处理器支持这个开关。关闭后该任务不会写入上下文，后续任务若依赖它的产物会报“流程上下文缺少任务产物”。

## 使用外部配置文件

默认读取打包在 classpath 中的这两个文件。部署时可以用环境变量指向外部文件，例如：

```text
HOTLINE_FLOW_SCENES=file:/path/to/flows.json
HOTLINE_FLOW_FUNCMAPS=file:/path/to/flow_funcmaps.properties
```

## 常见启动报错

| 报错内容 | 原因 |
| --- | --- |
| `场景 X 任务 Y 缺少 order` / `缺少 fmap` | 任务缺少必填字段 |
| `场景 X 任务 Y 的 order 不是整数` | `order` 写成了非整数 |
| `funcmap 未配置映射键：flow_9` | `flows.json` 引用的键没有在 properties 中登记 |
| `处理器类不存在` | properties 中的类名写错或类已被移动 |
| `处理器未实现 FlowItemProcessor` | 类没有实现处理器接口 |
| `处理器无法实例化` | 既不是 Spring Bean，又没有无参构造器 |
| `流程场景必须是非空对象` | 场景下没有任何任务 |
