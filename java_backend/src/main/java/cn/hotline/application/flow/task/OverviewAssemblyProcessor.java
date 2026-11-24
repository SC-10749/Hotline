package cn.hotline.application.flow.task;

import cn.hotline.api.dto.CapabilityOverviewView;
import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;

/** 总览合并：将并行采集的三路产物组装为能力总览视图。 */
@Component
public class OverviewAssemblyProcessor extends AbstractFlowProcessor {

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        Map<?, ?> pythonStatus = context.require(FlowKeys.PYTHON_STATUS, Map.class);
        Map<?, ?> skillCatalog = context.require(FlowKeys.SKILL_CATALOG, Map.class);
        Map<?, ?> harnessOverview = context.require(FlowKeys.HARNESS_OVERVIEW, Map.class);
        CapabilityOverviewView overview = new CapabilityOverviewView(
                Instant.now().toString(),
                context.flowId(),
                toStringKeyMap(pythonStatus),
                toStringKeyMap(skillCatalog),
                toStringKeyMap(harnessOverview));
        context.put(FlowKeys.OVERVIEW_RESULT, overview);
    }

    private static Map<String, Object> toStringKeyMap(Map<?, ?> source) {
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        source.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    }
}
