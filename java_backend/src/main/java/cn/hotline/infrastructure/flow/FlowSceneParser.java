package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowItemProcessor;
import cn.hotline.domain.flow.FlowScene;
import cn.hotline.domain.flow.FlowTask;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * 流程配置解析：abjson（场景 → 任务 → order/fmap/参数）→ FlowScene 列表。
 * 结构对齐 pandora-search-music 的 abtest_strategy.json：
 * <pre>
 * { "&lt;scene&gt;": { "&lt;taskKey&gt;": { "order": "0", "fmap": "flow_1", ...任务参数 } } }
 * </pre>
 * order 兼容字符串与数字；fmap 经 funcmap 映射到处理器；任务按 order 稳定排序
 * （相同 order 保持声明顺序），组内的额外字段全部作为任务参数透传。
 */
public final class FlowSceneParser {

    private final ObjectMapper objectMapper;

    public FlowSceneParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Map<String, FlowScene> parse(String json, Function<String, FlowItemProcessor> processorResolver) {
        JsonNode root;
        try {
            root = objectMapper.readTree(json);
        } catch (JsonProcessingException exception) {
            throw new FlowConfigurationException("流程配置不是合法 JSON", exception);
        }
        if (root == null || !root.isObject() || root.isEmpty()) {
            throw new FlowConfigurationException("流程配置必须是非空对象（场景 → 任务）");
        }
        Map<String, FlowScene> scenes = new LinkedHashMap<>();
        root.fields().forEachRemaining(sceneEntry -> {
            String sceneKey = sceneEntry.getKey();
            JsonNode sceneNode = sceneEntry.getValue();
            if (!sceneNode.isObject() || sceneNode.isEmpty()) {
                throw new FlowConfigurationException("流程场景必须是非空对象：" + sceneKey);
            }
            List<FlowTask> tasks = new ArrayList<>();
            sceneNode.fields().forEachRemaining(taskEntry -> tasks.add(parseTask(sceneKey, taskEntry, processorResolver)));
            tasks.sort(Comparator.comparingInt(FlowTask::order));
            scenes.put(sceneKey, new FlowScene(sceneKey, tasks));
        });
        return Collections.unmodifiableMap(scenes);
    }

    private FlowTask parseTask(String sceneKey, Map.Entry<String, JsonNode> taskEntry,
                               Function<String, FlowItemProcessor> processorResolver) {
        String taskKey = taskEntry.getKey();
        JsonNode taskNode = taskEntry.getValue();
        String location = "场景 " + sceneKey + " 任务 " + taskKey;
        if (!taskNode.isObject()) {
            throw new FlowConfigurationException(location + " 必须是对象");
        }
        int order = parseOrder(location, taskNode.get("order"));
        JsonNode fmapNode = taskNode.get("fmap");
        if (fmapNode == null || !fmapNode.isTextual() || fmapNode.textValue().isBlank()) {
            throw new FlowConfigurationException(location + " 缺少 fmap");
        }
        String fmapKey = fmapNode.textValue().trim();
        FlowItemProcessor processor;
        try {
            processor = processorResolver.apply(fmapKey);
        } catch (FlowConfigurationException exception) {
            throw new FlowConfigurationException(location + " 处理器解析失败：" + exception.getMessage(), exception);
        }
        if (processor == null) {
            throw new FlowConfigurationException(location + " 处理器解析结果为空：" + fmapKey);
        }
        Map<String, Object> params = new LinkedHashMap<>();
        taskNode.fields().forEachRemaining(field -> params.put(field.getKey(), valueOf(field.getValue())));
        params.put("_scene", sceneKey);
        params.put("_task", taskKey);
        return new FlowTask(taskKey, order, Collections.unmodifiableMap(params), processor);
    }

    private int parseOrder(String location, JsonNode orderNode) {
        if (orderNode == null || orderNode.isNull()) {
            throw new FlowConfigurationException(location + " 缺少 order");
        }
        if (orderNode.isNumber()) {
            if (!orderNode.canConvertToInt()) {
                throw new FlowConfigurationException(location + " 的 order 必须是整数：" + orderNode);
            }
            return orderNode.intValue();
        }
        if (orderNode.isTextual()) {
            try {
                return Integer.parseInt(orderNode.textValue().trim());
            } catch (NumberFormatException exception) {
                throw new FlowConfigurationException(location + " 的 order 不是整数：" + orderNode.textValue());
            }
        }
        throw new FlowConfigurationException(location + " 的 order 类型不受支持：" + orderNode);
    }

    private static Object valueOf(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isTextual()) {
            return node.textValue();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        if (node.isInt()) {
            return node.intValue();
        }
        if (node.isLong()) {
            return node.longValue();
        }
        if (node.isNumber()) {
            return node.doubleValue();
        }
        return node;
    }
}
