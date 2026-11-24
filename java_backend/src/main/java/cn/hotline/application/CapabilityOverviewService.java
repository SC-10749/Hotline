package cn.hotline.application;

import cn.hotline.api.dto.CapabilityOverviewView;
import cn.hotline.application.flow.FlowEngine;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Service;

/**
 * 能力总览入口：驱动 capability-overview 场景——三路采集任务同 order
 * 并行执行，随后串行合并；单个下游不可用时降级而非整体失败。
 */
@Service
public class CapabilityOverviewService {

    private final FlowEngine flowEngine;

    public CapabilityOverviewService(FlowEngine flowEngine) {
        this.flowEngine = flowEngine;
    }

    public CapabilityOverviewView overview() {
        FlowContext context = new FlowContext(FlowKeys.SCENE_CAPABILITY_OVERVIEW);
        flowEngine.execute(FlowKeys.SCENE_CAPABILITY_OVERVIEW, context);
        return context.require(FlowKeys.OVERVIEW_RESULT, CapabilityOverviewView.class);
    }
}
