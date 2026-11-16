package cn.hotline.application.flow.task;

import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.Map;

/** 技能目录采集（GET /skill/list，解封套取 data）；不可用时降级标记，不拖垮总览。 */
@Component
public class SkillCatalogProcessor extends AbstractFlowProcessor {

    private final PythonCapabilityPort pythonCapabilityPort;

    public SkillCatalogProcessor(PythonCapabilityPort pythonCapabilityPort) {
        this.pythonCapabilityPort = pythonCapabilityPort;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        try {
            context.put(FlowKeys.SKILL_CATALOG, pythonCapabilityPort.skillCatalog());
        } catch (PythonUnavailableException exception) {
            context.put(FlowKeys.SKILL_CATALOG, Map.<String, Object>of("unavailable", true));
        }
    }
}
