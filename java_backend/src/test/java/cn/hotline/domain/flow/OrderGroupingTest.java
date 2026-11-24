package cn.hotline.domain.flow;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class OrderGroupingTest {

    @Test
    void groupsOnlyConsecutiveTasksWithEqualOrder() {
        List<FlowTask> tasks = List.of(task("a", 0), task("b", 0), task("c", 1), task("d", 0));

        List<List<FlowTask>> groups = OrderGrouping.group(tasks);

        assertThat(groups).hasSize(3);
        assertThat(groups.get(0)).extracting(FlowTask::key).containsExactly("a", "b");
        assertThat(groups.get(1)).extracting(FlowTask::key).containsExactly("c");
        assertThat(groups.get(2)).extracting(FlowTask::key).containsExactly("d");
    }

    @Test
    void equalOrdersAcrossWholeInputStayInOneGroup() {
        List<List<FlowTask>> groups = OrderGrouping.group(List.of(task("a", 1), task("b", 1), task("c", 1)));
        assertThat(groups).hasSize(1);
        assertThat(groups.get(0)).hasSize(3);
    }

    @Test
    void emptyInputYieldsNoGroups() {
        assertThat(OrderGrouping.group(List.of())).isEmpty();
    }

    private static FlowTask task(String key, int order) {
        return new FlowTask(key, order, Map.of(), (context, params) -> {
        });
    }
}
