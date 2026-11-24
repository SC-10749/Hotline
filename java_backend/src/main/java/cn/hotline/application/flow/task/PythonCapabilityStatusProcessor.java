package cn.hotline.application.flow.task;

import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.capability.PythonHealth;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

/** Python 健康与就绪状态探测；不可用时降级为 UNAVAILABLE，不拖垮总览。 */
@Component
public class PythonCapabilityStatusProcessor extends AbstractFlowProcessor {

    private final PythonCapabilityPort pythonCapabilityPort;

    public PythonCapabilityStatusProcessor(PythonCapabilityPort pythonCapabilityPort) {
        this.pythonCapabilityPort = pythonCapabilityPort;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("health", probe(pythonCapabilityPort::health));
        status.put("readiness", probe(pythonCapabilityPort::readiness));
        context.put(FlowKeys.PYTHON_STATUS, status);
    }

    private Map<String, Object> probe(Supplier<PythonHealth> call) {
        try {
            PythonHealth health = call.get();
            Map<String, Object> view = new LinkedHashMap<>();
            view.put("status", health.status());
            view.put("service", health.service());
            view.put("version", health.version());
            return view;
        } catch (PythonUnavailableException exception) {
            return Map.of("status", "UNAVAILABLE");
        }
    }
}
