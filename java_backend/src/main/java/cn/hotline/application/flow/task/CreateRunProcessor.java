package cn.hotline.application.flow.task;

import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.capability.PythonCapabilityPort;
import cn.hotline.domain.execution.ExecutionRun;
import cn.hotline.domain.execution.ExecutionSubmission;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 调用 Python POST /execution/runs 创建运行；上游 503/409/404/400
 * 由适配器转换为类型化异常，交由统一错误契约映射。
 */
@Component
public class CreateRunProcessor extends AbstractFlowProcessor {

    private final PythonCapabilityPort pythonCapabilityPort;

    public CreateRunProcessor(PythonCapabilityPort pythonCapabilityPort) {
        this.pythonCapabilityPort = pythonCapabilityPort;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        ExecutionSubmission submission = context.require(FlowKeys.SUBMISSION, ExecutionSubmission.class);
        ExecutionRun run = pythonCapabilityPort.createExecutionRun(submission);
        context.put(FlowKeys.EXECUTION_RUN, run);
    }
}
