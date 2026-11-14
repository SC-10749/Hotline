package cn.hotline.domain.flow;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 流程共享上下文。对应 pandora-search-music 中随 ItemReader 创建、
 * 在处理器之间传递的流程 item：同一场景内的全部任务共享一份状态，
 * 结果通过约定键写入、后续任务读取，而不是依赖返回值传递。
 */
public final class FlowContext {

    private final String flowId;
    private final String scene;
    private final long startedAtNanos;
    private final Map<String, Object> attributes = new ConcurrentHashMap<>();

    public FlowContext(String scene) {
        this.scene = scene;
        this.flowId = UUID.randomUUID().toString();
        this.startedAtNanos = System.nanoTime();
    }

    public String scene() {
        return scene;
    }

    public String flowId() {
        return flowId;
    }

    public long elapsedMillis() {
        return (System.nanoTime() - startedAtNanos) / 1_000_000L;
    }

    public void put(String key, Object value) {
        attributes.put(key, value);
    }

    public <T> T require(String key, Class<T> type) {
        Object value = attributes.get(key);
        if (value == null) {
            throw new FlowExecutionException("流程上下文缺少任务产物：" + key);
        }
        return type.cast(value);
    }
}
