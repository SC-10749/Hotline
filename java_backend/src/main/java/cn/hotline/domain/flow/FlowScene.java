package cn.hotline.domain.flow;

import java.util.List;

/** 流程场景：名称 + 已按 order 稳定排序的任务列表。 */
public record FlowScene(String key, List<FlowTask> tasks) {

    public FlowScene {
        tasks = List.copyOf(tasks);
    }
}
