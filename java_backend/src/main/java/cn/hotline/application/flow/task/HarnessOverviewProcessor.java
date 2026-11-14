package cn.hotline.application.flow.task;

import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.Map;

/** 自动化总览采集（GET /harness/overview，原始 JSON 透传）；不可用时降级标记，不拖垮总览。 */
@Component
public class HarnessOverviewProcessor extends AbstractFlowProcessor {

    private final PythonCapabilityPort pythonCapabilityPort;

    public HarnessOverviewProcessor(PythonCapabilityPort pythonCapabilityPort) {
        this.pythonCapabilityPort = pythonCapabilityPort;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        try {
            context.put(FlowKeys.HARNESS_OVERVIEW, pythonCapabilityPort.harnessOverview());
        } catch (PythonUnavailableException exception) {
            context.put(FlowKeys.HARNESS_OVERVIEW, Map.<String, Object>of("unavailable", true));
        }
    }
}
