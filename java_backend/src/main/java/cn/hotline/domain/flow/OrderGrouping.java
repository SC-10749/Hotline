package cn.hotline.domain.flow;

import java.util.ArrayList;
import java.util.List;

/**
 * 按 order 分组。沿用 pandora-search-music CollectionUtils.groupListBySequence 的
 * “连续相等才同组”语义：排序后相同 order 的相邻任务归为一组，组内并行、组间串行。
 * 解析阶段保证任务已按 order 稳定排序，因此相同 order 的任务必然相邻。
 */
public final class OrderGrouping {

    private OrderGrouping() {
    }

    public static List<List<FlowTask>> group(List<FlowTask> sortedTasks) {
        List<List<FlowTask>> groups = new ArrayList<>();
        if (sortedTasks.isEmpty()) {
            return groups;
        }
        List<FlowTask> current = new ArrayList<>();
        current.add(sortedTasks.get(0));
        groups.add(current);
        FlowTask previous = sortedTasks.get(0);
        for (int index = 1; index < sortedTasks.size(); index++) {
            FlowTask next = sortedTasks.get(index);
            if (previous.order() != next.order()) {
                current = new ArrayList<>();
                previous = next;
                groups.add(current);
            }
            current.add(next);
        }
        return groups;
    }
}
