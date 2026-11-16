package cn.hotline.api.dto;

import java.util.Map;

/**
 * 能力总览视图：由 capability-overview 场景聚合产出。
 * python/skills/harness 任一采集失败时为 {@code {"unavailable": true}} 降级标记。
 */
public record CapabilityOverviewView(
        String generatedAt,
        String requestId,
        Map<String, Object> python,
        Map<String, Object> skills,
        Map<String, Object> harness) {
}
